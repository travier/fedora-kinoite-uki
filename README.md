# Manifests for rpm-ostree based Fedora variants

This is the configuration needed to create
[rpm-ostree](https://coreos.github.io/rpm-ostree/) based variants of Fedora.
Each variant is described in a YAML
[treefile](https://coreos.github.io/rpm-ostree/treefile/) which is then used by
rpm-ostree to compose an ostree commit with the package requested.

In the Fedora infrastructure, this happens via
[pungi](https://pagure.io/pungi-fedora) with
[Lorax](https://github.com/weldr/lorax)
([templates](https://pagure.io/fedora-lorax-templates)).

## Fedora Silverblue

- Website: https://silverblue.fedoraproject.org/ ([sources](https://github.com/fedora-silverblue/silverblue-site))
- Documentation: https://docs.fedoraproject.org/en-US/fedora-silverblue/ ([sources](https://github.com/fedora-silverblue/silverblue-docs))
- Issue tracker: https://github.com/fedora-silverblue/issue-tracker/issues

## Fedora Kinoite

- Website: https://kinoite.fedoraproject.org/ ([sources](https://pagure.io/fedora-kde/kinoite-site))
- Documentation: https://docs.fedoraproject.org/en-US/fedora-kinoite/ ([sources](https://pagure.io/fedora-kde/kinoite-docs))
- Issue tracker: https://pagure.io/fedora-kde/SIG/issues

## Building

Instructions to perform a local build of Silverblue:

```
# Clone the config
git clone https://pagure.io/workstation-ostree-config && cd workstation-ostree-config

# Prepare directories
mkdir -p repo cache
ostree --repo=repo init --mode=archive

# Build (compose) the variant of your choice
sudo rpm-ostree compose tree --repo=repo --cachedir=cache fedora-silverblue.yaml

# Update summary file
ostree summary --repo=repo --update
```

## Testing

Instructions to test the resulting build:

- First, serve the ostree repo using an HTTP server. You can use any static file server. For example using <https://github.com/TheWaWaR/simple-http-server>:

  ```
  simple-http-server --index --ip 192.168.122.1 --port 8000
  ```

- Then, on an already installed Silverblue system:

```
# Add an ostree remote
sudo ostree remote add testremote http://192.168.122.1:8000/repo --no-gpg-verify

# Pin the currently deployed (and probably working) version
sudo ostree admin pin 0

# List refs from variant remote
sudo ostree remote refs testremote

# Switch to your variant
sudo rpm-ostree rebase testremote:fedora/rawhide/x86_64/silverblue

# Reboot and test!
```

## Branching instructions for new Fedora releases

Follow those steps during the Fedora branch process in Fedora:

### Fedora Ansible

Make a PR similar to
[ansible#1318](https://pagure.io/fedora-infra/ansible/pull-request/1318) in
[fedora-infra/ansible](https://pagure.io/fedora-infra/ansible).

### On Rawhide / main branch

```
sed -i "s/40/41/g" *.repo *.yaml comps-sync.py
mv fedora-40.repo fedora-41.repo
mv fedora-40-updates.repo fedora-41-updates.repo
sed -i "s/41/42/g" README.md
sed -i "s/40/41/g" README.md
```

### On the new branch (f40)

```
rm fedora-rawhide.repo
sed -i "/- fedora-rawhide/d" *.yaml
sed -i "s/# - fedora-40/- fedora-40/" *.yaml
sed -i "s/ref: fedora\/rawhide/ref: fedora\/40/" *.yaml
```

## Historical references

Building and testing instructions:

- https://dustymabe.com/2017/10/05/setting-up-an-atomic-host-build-server/
- https://dustymabe.com/2017/08/08/how-do-we-create-ostree-repos-and-artifacts-in-fedora/
- https://www.projectatomic.io/blog/2017/12/compose-custom-ostree/
- https://www.projectatomic.io/docs/compose-your-own-tree/

For some background, see:

- <https://fedoraproject.org/wiki/Workstation/AtomicWorkstation>
- <https://fedoraproject.org/wiki/Changes/WorkstationOstree>
- <https://fedoraproject.org/wiki/Changes/Silverblue>
- <https://fedoraproject.org/wiki/Changes/Fedora_Kinoite>

Note also this repo obsoletes https://pagure.io/atomic-ws
