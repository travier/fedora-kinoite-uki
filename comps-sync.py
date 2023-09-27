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

parser = argparse.ArgumentParser()
parser.add_argument("--save", help="Write changes", action='store_true')
parser.add_argument("src", help="Source path")

args = parser.parse_args()

print("Syncing packages common to all desktops:")

manifest_path = 'fedora-common-ostree-pkgs.yaml'
manifest_packages = load_packages_from_manifest(manifest_path)

with open('comps-sync-exclude-list.yml', encoding='UTF-8') as f:
    doc = yaml.safe_load(f)
    comps_exclude_list = doc['exclude_list']
    comps_include_list = doc['include_list']
    comps_exclude_list_groups = doc['exclude_list_groups']
    comps_desktop_exclude_list = doc['desktop_exclude_list']
    comps_exclude_list_all = [re.compile(x) for x in doc['exclude_list_all_regexp']]

# Parse comps, and build up a set of all packages so we
# can find packages not listed in comps *at all*, beyond
# just the workstation environment.
comps = libcomps.Comps()
comps.fromxml_f(args.src)

# Parse the workstation-product environment, gathering
# default or mandatory packages.
ws_env_name = 'workstation-product-environment'
ws_ostree_name = 'workstation-ostree-support'
ws_environ = comps.environments[ws_env_name]
ws_pkgs = {}
for gid in ws_environ.group_ids:
    if gid.name in comps_exclude_list_groups:
        continue
    exclude_list = comps_exclude_list.get(gid.name, set())
    for arch in ARCHES:
        filtered = comps.arch_filter([arch])
        group = filtered.groups_match(id=gid.name)[0]
        for pkg in group.packages:
            pkgname = pkg.name
            if pkg.type not in (libcomps.PACKAGE_TYPE_DEFAULT,
                                libcomps.PACKAGE_TYPE_MANDATORY):
                continue
            if pkgname in exclude_list or is_exclude_listed(pkgname):
                continue
            pkgdata = ws_pkgs.get(pkgname)
            if pkgdata is None:
                ws_pkgs[pkgname] = pkgdata = (pkg.type, set([gid.name]), set([arch]))
            if (pkgdata[0] == libcomps.PACKAGE_TYPE_DEFAULT and
                pkg.type == libcomps.PACKAGE_TYPE_MANDATORY):
                ws_pkgs[pkgname] = pkgdata = (pkg.type, pkgdata[1], pkgdata[2])
            pkgdata[1].add(gid.name)
            pkgdata[2].add(arch)

ws_ostree_pkgs = set()
for pkg in comps.groups_match(id=ws_ostree_name)[0].packages:
    if not is_exclude_listed(pkg.name, comps_exclude_list_all):
        ws_ostree_pkgs.add(pkg.name)

comps_unknown = set()
for arch in manifest_packages:
    for pkg in manifest_packages[arch]:
        if arch == "all":
            if pkg in ws_pkgs and set(ws_pkgs[pkg][2]) == set(ARCHES):
                continue
        else:
            if pkg in ws_pkgs and arch in ws_pkgs[pkg][2]:
                continue
        if (pkg not in comps_include_list and
            pkg not in ws_ostree_pkgs):
            comps_unknown.add((pkg, arch))

# Look for packages in the manifest but not in comps at all
n_manifest_new = len(comps_unknown)
if n_manifest_new == 0:
    print("  - All manifest packages are already listed in comps.")
else:
    print(f'  - {n_manifest_new} packages not in {ws_env_name}:')
    for (pkg, arch) in sorted(comps_unknown, key = lambda x: x[0]):
        print(f'    {pkg} (arch: {arch})')
        manifest_packages[arch].remove(pkg)

# Look for packages in workstation but not in the manifest
ws_added = {}
for (pkg,data) in ws_pkgs.items():
    if set(ARCHES) == set(data[2]):
        if pkg not in manifest_packages['all']:
            ws_added[pkg] = data
            manifest_packages['all'].add(pkg)
    else:
        for arch in data[2]:
            if pkg not in manifest_packages[arch]:
                manifest_packages[arch].add(pkg)
                if pkg not in ws_added:
                    ws_added[pkg] = (data[0], data[1], set([arch]))
                else:
                    ws_added[pkg][2].add(arch)

n_comps_new = len(ws_added)
if n_comps_new == 0:
    print("  - All comps packages are already listed in manifest.")
else:
    print(f'  - {n_comps_new} packages not in manifest:')
    for pkg in sorted(ws_added):
        (req, groups, arches) = ws_added[pkg]
        print('    {} ({}, groups: {}, arches: {})'.format(pkg, format_pkgtype(req), ', '.join(groups), ', '.join(arches)))

if (n_manifest_new > 0 or n_comps_new > 0) and args.save:
    write_manifest(manifest_path, manifest_packages)

# List of comps groups used for each desktop
desktops_comps_groups = {
    "gnome": ["gnome-desktop", "base-x"],
    "kde": ["kde-desktop", "base-x"],
    "xfce": ["xfce-desktop", "base-x"],
    "lxqt": ["lxqt-desktop", "base-x"],
    "deepin": ["deepin-desktop", "base-x"],
    "mate": ["mate-desktop", "base-x"],
    "sway": ["swaywm", "swaywm-extended"],
    "cinnamon": ["cinnamon-desktop", "base-x"],
    "budgie": ["budgie-desktop", "budgie-desktop-apps", "base-x"]
}

# Generate treefiles for all desktops
for desktop, groups in desktops_comps_groups.items():
    print()
    print(f'Syncing packages for {desktop}:')

    manifest_path = f'{desktop}-desktop-pkgs.yaml'
    manifest_packages = load_packages_from_manifest(manifest_path)

    # Filter packages in the comps desktop group using the exclude_list
    comps_group_pkgs = {}
    for arch in ARCHES:
        filtered = comps.arch_filter([arch])
        for group in groups:
            for pkg in filtered.groups_match(id=group)[0].packages:
                pkgname = pkg.name
                exclude_list = comps_desktop_exclude_list.get(group, set())
                if pkgname in exclude_list or is_exclude_listed(pkgname, comps_exclude_list_all):
                    continue
                if pkgname in comps_group_pkgs:
                    comps_group_pkgs[pkgname].add(arch)
                else:
                    comps_group_pkgs[pkgname] = set([arch])

    comps_unknown = set()
    for arch in manifest_packages:
        for pkg in manifest_packages[arch]:
            if arch == "all":
                if pkg in comps_group_pkgs and set(comps_group_pkgs[pkg]) == set(ARCHES):
                    continue
            else:
                if pkg in comps_group_pkgs and arch in comps_group_pkgs[pkg]:
                    continue
            comps_unknown.add((pkg, arch))

    # Look for packages in the manifest but not in comps at all
    n_manifest_new = len(comps_unknown)
    if n_manifest_new == 0:
        print("  - All manifest packages are already listed in comps.")
    else:
        print(f'  - {n_manifest_new} packages not in {ws_env_name}:')
        for (pkg, arch) in sorted(comps_unknown, key = lambda x: x[0]):
            print(f'    {pkg} (arch: {arch})')
            manifest_packages[arch].remove(pkg)


    # Look for packages in comps but not in the manifest
    desktop_pkgs_added = {}
    for (pkg, parches) in comps_group_pkgs.items():
        if set(ARCHES) == set(parches):
            if pkg not in manifest_packages['all']:
                desktop_pkgs_added[pkg] = parches
                manifest_packages['all'].add(pkg)
        else:
            for arch in parches:
                if pkg not in manifest_packages[arch]:
                    manifest_packages[arch].add(pkg)
                    if pkg not in desktop_pkgs_added:
                        desktop_pkgs_added[pkg] = set([arch])
                    else:
                        desktop_pkgs_added[pkg].add(arch)

    n_comps_new = len(desktop_pkgs_added)
    if n_comps_new == 0:
        print("  - All comps packages are already listed in manifest.")
    else:
        print(f'  - {n_comps_new} packages not in {desktop} manifest:')
        for pkg in sorted(desktop_pkgs_added):
            arches = desktop_pkgs_added[pkg]
            print('    {} (arches: {})'.format(pkg, ', '.join(arches)))

    # Update manifest
    if (n_manifest_new > 0 or n_comps_new > 0) and args.save:
        write_manifest(manifest_path, manifest_packages, include="fedora-common-ostree.yaml")
