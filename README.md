# giternity

[![Version](https://img.shields.io/pypi/v/giternity.svg)](https://pypi.org/project/giternity/)
[![pyversions](https://img.shields.io/pypi/pyversions/giternity.svg)](https://pypi.org/project/giternity/)
[![Downloads](https://www.cpu.re/static/giternity/downloads.svg)](https://www.cpu.re/static/giternity/downloads-by-python-version.txt)
[![License](https://img.shields.io/badge/License-GPLv3+-blue.svg)](https://github.com/rahiel/giternity/blob/master/LICENSE.txt)

Giternity is a tool to mirror git repositories from GitHub.
You can specify a username/organization to mirror all their repositories, or just individual repos.
It retrieves some repo metadata so they can be nicely served with [cgit][].
Run giternity periodically to update the mirrors.

An example result is [git.cpu.re][]. Follow the [tutorial][] to host your own.

[cgit]: https://git.zx2c4.com/cgit/about/
[git.cpu.re]: https://git.cpu.re/
[tutorial]: https://www.rahielkasim.com/mirror-git-repositories-and-serve-them-with-cgit/

# Installation

Giternity is packaged via PyPi, the Python Package Index.
Required packages:
- Python 3
- Python 3 `pip` (if your distro packages it separately)
- git

``` shell
sudo pip3 install giternity
```

# Configuration

The configuration file by default is located at `/etc/giternity.toml`.
See the example [giternity.toml](/examples/giternity.toml) for a list of all options.

With the configuration in place you simply run `giternity`, or `giternity -c $YOUR_CONFIG_FILE` if you want to place it somewhere else.

## cron

Giternity is intended for use as an unsupervised cron.
See the example [giternity.cron](/examples/giternity.cron) for a possible `/etc/cron.d/giternity`.

Note that it is recommended to run Giternity as an unprivileged or "sandbox" user if possible.
For example one could have a `git-data` group which owns the `/srv/git` data directory.
`http` (for cgit), `git` (for gitosis, gitolite or just bare git-shell) and `giternity` could all be group members.

## cgit

Your git mirrors are now suitable to serve with cgit. Customize your
`/etc/cgitrc` as you like and add the following to the bottom:

```ini
# the giternity git_data_path as you configured it
scan-path=/srv/git/
# giternity writes this file to track the last-modified date of mirroed repos
agefile=info/web/last-modified
# infer section (github user / group) from the first repo path segment
section-from-path=1
```
