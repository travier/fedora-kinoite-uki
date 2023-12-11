#!/usr/bin/python3

'''
Usage: ./comps-sync.py /path/to/comps-f39.xml.in

Can both remove packages from the manifest which are not mentioned in comps,
and add packages from comps.
'''

import argparse
import re
import sys
import yaml
import libcomps

ARCHES = ("x86_64", "aarch64", "ppc64le")

def fatal(msg):
    '''Print the error message and exit.'''
    print(msg, file = sys.stderr)
    sys.exit(1)

def format_pkgtype(pkgtype):
    '''Return a printable string from a libcomps package type.'''
    if pkgtype == libcomps.PACKAGE_TYPE_DEFAULT:
        return 'default'
    if pkgtype == libcomps.PACKAGE_TYPE_MANDATORY:
        return 'mandatory'
    assert False

def write_manifest(fpath, pkgs, include=None):
    '''Write the package list in a manifest.'''
    with open(fpath, 'w', encoding='UTF-8') as f:
        f.write("# DO NOT EDIT! This content is generated from comps-sync.py\n")
        if include is not None:
            f.write(f'include: {include}\n')
        f.write("packages:\n")
        for pkg in sorted(pkgs['all']):
            f.write(f'  - {pkg}\n')
        for arch in ARCHES:
            if pkgs[arch]:
                f.write(f"packages-{arch}:\n")
                for pkg in sorted(pkgs[arch]):
                    f.write(f'  - {pkg}\n')
        print(f'Wrote {fpath}')

def is_exclude_listed(pkgname, exclude_list_regexp):
    '''Check if pkgname is in the exclude list.'''
    for br in exclude_list_regexp:
        if br.match(pkgname):
            return True
    return False

def load_packages_from_manifest(manifest_path):
    '''Load the list of packages from an rpm-ostree manifest file.'''
    with open(manifest_path, encoding='UTF-8') as f:
        manifest = yaml.safe_load(f)
    manifest_packages = {}
    manifest_packages['all'] = set(manifest['packages'])
    for arch in ARCHES:
        if f'packages-{arch}' in manifest:
            manifest_packages[arch] = set(manifest[f'packages-{arch}'])
        else:
            manifest_packages[arch] = set()
    return manifest_packages

def load_packages_from_comps_group(comps_group_packages, comps, groupname, exclude_list, exclude_list_regexp):
    '''Load packages from a comps group, storing the group, type and arches.'''
    for arch in ARCHES:
        filtered = comps.arch_filter([arch])
        group = filtered.groups_match(id=groupname)[0]
        for pkg in group.packages:
            pkgname = pkg.name
            if pkg.type not in (libcomps.PACKAGE_TYPE_DEFAULT,
                                libcomps.PACKAGE_TYPE_MANDATORY):
                continue
            if pkgname in exclude_list or is_exclude_listed(pkgname, exclude_list_regexp):
                continue
            pkgdata = comps_group_packages.get(pkgname)
            if pkgdata is None:
                comps_group_packages[pkgname] = pkgdata = (pkg.type, set([groupname]), set([arch]))
            if (pkgdata[0] == libcomps.PACKAGE_TYPE_DEFAULT and
                pkg.type == libcomps.PACKAGE_TYPE_MANDATORY):
                comps_group_packages[pkgname] = pkgdata = (pkg.type, pkgdata[1], pkgdata[2])
            pkgdata[1].add(groupname)
            pkgdata[2].add(arch)
    return comps_group_packages

def compare_comps_manifest_package_lists(comps_group_pkgs, manifest_packages):
    '''Compare the list of packages in the comps and the manifests and return the difference.'''
    # Look for packages in the manifest but not in the comps
    comps_unknown = set()
    for arch in manifest_packages:
        for pkg in manifest_packages[arch]:
            if arch == "all":
                if pkg in comps_group_pkgs and set(comps_group_pkgs[pkg][2]) == set(ARCHES):
                    continue
            else:
                if pkg in comps_group_pkgs and arch in comps_group_pkgs[pkg][2]:
                    continue
            comps_unknown.add((pkg, arch))

    # Look for packages in comps but not in the manifest
    pkgs_added = {}
    for (pkg, pkgdata) in comps_group_pkgs.items():
        if set(ARCHES) == set(pkgdata[2]):
            if pkg not in manifest_packages['all']:
                pkgs_added[pkg] = pkgdata
        else:
            for arch in pkgdata[2]:
                if pkg not in manifest_packages[arch]:
                    if pkg not in pkgs_added:
                        pkgs_added[pkg] = (pkgdata[0], pkgdata[1], set([arch]))
                    else:
                        pkgs_added[pkg][2].add(arch)

    return comps_unknown, pkgs_added

def update_manifests_from_groups(comps, groups, path, desktop, save, comps_exclude_list, comps_exclude_list_all):
    manifest_packages = load_packages_from_manifest(path)

    comps_group_pkgs = {}
    for group in groups:
        exclude_list = comps_exclude_list.get(group, set())
        comps_group_pkgs = load_packages_from_comps_group(comps_group_pkgs, comps, group, exclude_list, comps_exclude_list_all)

    (comps_unknown, pkgs_added) = compare_comps_manifest_package_lists(comps_group_pkgs, manifest_packages)

    n_manifest_new = len(comps_unknown)
    n_comps_new = len(pkgs_added)

    if desktop == "common":
        print(f'Syncing common packages:\t+{n_comps_new}, -{n_manifest_new}')
    else:
        print(f'Syncing packages for {desktop}:\t+{n_comps_new}, -{n_manifest_new}')
    if n_manifest_new != 0:
        for (pkg, arch) in sorted(comps_unknown, key = lambda x: x[0]):
            manifest_packages[arch].remove(pkg)
            print(f'  - {pkg} (arches: {arch})')
    if n_comps_new != 0:
        for pkg in sorted(pkgs_added):
            (req, groups, arches) = pkgs_added[pkg]
            if set(ARCHES) == arches:
                manifest_packages['all'].add(pkg)
                print('  + {} ({}, groups: {}, arches: all)'.format(pkg, format_pkgtype(req), ', '.join(groups)))
            else:
                for arch in arches:
                    manifest_packages[arch].add(pkg)
                print('  + {} ({}, groups: {}, arches: {})'.format(pkg, format_pkgtype(req), ', '.join(groups), ', '.join(arches)))

    if (n_manifest_new > 0 or n_comps_new > 0) and save:
        if desktop == "common":
            write_manifest(path, manifest_packages)
        else:
            write_manifest(path, manifest_packages, include="fedora-common-ostree.yaml")

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--save", help="Write changes", action='store_true')
    parser.add_argument("src", help="Source path")

    args = parser.parse_args()

    with open('comps-sync-exclude-list.yml', encoding='UTF-8') as f:
        doc = yaml.safe_load(f)
        comps_exclude_list = doc['exclude_list']
        comps_exclude_list_groups = doc['exclude_list_groups']
        comps_desktop_exclude_list = doc['desktop_exclude_list']
        comps_exclude_list_all = [re.compile(x) for x in doc['exclude_list_all_regexp']]

    # Parse comps, and build up a set of all packages so we can find packages not
    # listed in comps *at all*, beyond just the workstation environment.
    comps = libcomps.Comps()
    comps.fromxml_f(args.src)

    # Parse the workstation-product environment to get the list of comps groups to
    # get packages from.
    groups = []
    for gid in comps.environments['workstation-product-environment'].group_ids:
        if gid.name in comps_exclude_list_groups:
            continue
        groups.append(gid.name)

    # Always include the packages from the workstation-ostree-support group
    groups.append('workstation-ostree-support')

    update_manifests_from_groups(comps, groups, 'fedora-common-ostree-pkgs.yaml', "common", args.save, comps_exclude_list, comps_exclude_list_all)

    # List of comps groups used for each desktop
    desktops_comps_groups = {
        "gnome": ["gnome-desktop", "base-x"],
        "kde": ["kde-desktop", "base-graphical"],
        "xfce": ["xfce-desktop", "xfce-apps", "xfce-extra-plugins", "base-x"],
        "lxqt": ["lxqt-desktop", "base-graphical"],
        "deepin": ["deepin-desktop", "base-x"],
        "mate": ["mate-desktop", "base-x"],
        "sway": ["swaywm", "swaywm-extended", "base-graphical"],
        "cinnamon": ["cinnamon-desktop", "base-x"],
        "budgie": ["budgie-desktop", "budgie-desktop-apps", "base-x"]
    }

    # Generate treefiles for all desktops
    for desktop, groups in desktops_comps_groups.items():
        print()
        update_manifests_from_groups(comps, groups, f'{desktop}-desktop-pkgs.yaml', desktop, args.save, comps_desktop_exclude_list, comps_exclude_list_all)

if __name__ == "__main__":
    main()
