#!/usr/bin/env python3
# Copyright (C) 2017-2018 Rahiel Kasim
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANT ABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
giternity - Mirror git repositories and retrieve metadata for cgit
"""

import argparse
import os
import re
import subprocess
import sys
import logging as log

from os.path import exists
from pwd import getpwnam
from subprocess import CalledProcessError, run
from typing import Optional

from colors import color
import requests
import toml


__version__ = "0.3.2"


def configure(git_data_path: str, checkout_path: str = None):
    try:
        try:
            getpwnam("giternity")
        except KeyError:
            run(["adduser", "giternity", "--system", "--no-create-home"],
                check=True)

        for path in [git_data_path, checkout_path]:
            if path:
                run(["mkdir", "-p", path], check=True)
                run(["chown", "-R", "giternity", path], check=True)

        cron = """SHELL=/bin/sh
PATH=/usr/local/sbin:/usr/local/bin:/sbin:/bin:/usr/sbin:/usr/bin

# m h dom mon dow user  command
0 * * * * giternity giternity\n"""

        with open("/etc/cron.d/giternity", "w") as f:
            f.write(cron)

    except (FileNotFoundError, PermissionError, CalledProcessError):
        print("Please run the configuration with root privileges: " +
              color("sudo giternity --configure", style="bold"))
        sys.exit(1)

    print(color("Everything is OK!", fg="green") + "\nHave fun using giternity!")


def mirror(url: str, path: str):
    if exists(path):
        run(["git", "-C", path, "remote", "update", "--prune"],
            stdout=subprocess.DEVNULL)
    else:
        run(["git", "clone", "--bare", "--mirror", url, path],
            stdout=subprocess.DEVNULL)

    os.makedirs(path + "info/web/", exist_ok=True)

    # set last modified date
    date = run(["git", "-C", path,
                "for-each-ref",
                "--sort=-authordate",
                "--count=1",
                "--format='%(authordate:iso8601)'"],
               stdout=subprocess.PIPE)

    with open(path + "info/web/last-modified", "wb") as f:
        f.write(date.stdout)


def clone(source: str, destination: str):
    if is_work_tree(destination):
        run(["git", "-C", destination, "pull"],
            stdout=subprocess.DEVNULL)
    else:
        run(["git", "clone", "--bare", source, destination],
            stdout=subprocess.DEVNULL)


def is_bare_repo(path: str):
    is_git = run(["git", "-C", path, "rev-parse", "--is-bare-repository"],
                 stdout=subprocess.PIPE,
                 stderr=subprocess.DEVNULL)\
                 .stdout\
                 .strip()

    return is_git == b"true"


def is_work_tree(path: str):
    is_work = run(["git", "-C", path, "rev-parse", "--is-inside-work-tree"],
                  stdout=subprocess.PIPE,
                  stderr=subprocess.DEVNULL)\
                  .stdout\
                  .strip()

    return is_work == b"true"


class GitHub:
    def __init__(self, cgit_url=None):
        session = requests.Session()
        session.headers.update({
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "giternity ({})".format(__version__)
        })
        self.s = session
        self.api = "https://api.github.com"
        self.cgit_url = cgit_url

    def get_repo(self, owner: str, repository: str):
        return self.s.get(self.api + "/repos/{}/{}".format(owner, repository))\
                     .json()

    def get_repos(self, user: str):
        (data, next_page) = self.get_repos_page(user, 1)
        while next_page:
            (d, next_page) = self.get_repos_page(user, next_page)
            data += d
        data = [r for r in data if not r["fork"]]
        return data

    def get_repos_page(self, user: str, page: int):
        result = self.s.get("{}/users/{}/repos?per_page=100&page={}"
                            .format(self.api, user, page))
        link_header = "Link" in result.headers and\
                      re.search('<[^>]+page=(\d+)>; rel="next"',
                                str(result.headers["Link"]))
        next_page = link_header and int(link_header.groups()[0])
        return (result.json(), next_page)

    def repo_to_cgitrc(self, data):
        cgitrc = []
        if self.cgit_url:
            local_url = self.cgit_url + data["full_name"]
            clone_url = "clone-url={} {}\n".format(local_url, data["clone_url"])

        else:
            clone_url = "clone-url={}\n".format(data["clone_url"])

        if data["description"]:
            desc = "desc={}\n".format(data["description"].replace("\n", ""))
        else:
            desc = "desc=Mysterious Project\n"

        if data["homepage"]:
            homepage = "homepage={}\n".format(data["homepage"])
            cgitrc.append(homepage)

        name = "name={}\n".format(data["name"])
        cgitrc += [clone_url, desc, name]
        return "".join(cgitrc)


def trailing_slash(path: Optional[str]):
    if path:
        return path if path.endswith("/") else path + "/"
    else:
        return None


parser = argparse.ArgumentParser(
  description="Mirror git repositories and retrieve metadata for cgit.",
  epilog="Homepage: https://github.com/rahiel/giternity")

parser.add_argument("--configure",
                    help="configure %(prog)s",
                    action="store_true")

parser.add_argument("--version",
                    action="version",
                    version="%(prog)s {}".format(__version__))

parser.add_argument("-c", "--config",
                    help="configuration file for %(prog)s",
                    dest="config_file",
                    default="/etc/giternity.toml")


def main():
    args = parser.parse_args()

    log.basicConfig(level=log.DEBUG,
                    format='%(name)-12s: %(levelname)-8s %(message)s')

    try:
        config = toml.load(args.config_file)
    except FileNotFoundError:
        print(color("No configuration file found!", fg="red"))
        print("Please place your configuration at "
              + color(args.config_file, style="bold"))
        sys.exit(1)

    git_data_path = trailing_slash(config.get("git_data_path", "/srv/git/"))
    checkout_path = trailing_slash(config.get("checkout_path"))
    cgit_url = trailing_slash(config.get("cgit_url"))
    checkout_suffix = trailing_slash(config.get("checkout_suffix", ""))

    if args.configure:
        return configure(git_data_path, checkout_path)

    if config.get("github") and config["github"].get("repositories"):
        gh = GitHub(cgit_url=cgit_url)
        for r in config["github"]["repositories"]:
            if "/" in r:
                path = git_data_path + r + checkout_suffix
                log.info("Mirroring repo %s (%s)", r, path)
                owner, name = r.split("/")
                url = "https://github.com/{}/{}.git".format(owner, name)
                repo = gh.get_repo(owner, name)
                mirror(url, path)
                with open(path + "cgitrc", "w") as f:
                    f.write(gh.repo_to_cgitrc(repo))
            else:
                log.info("Mirroring group %s", r)
                for repo in gh.get_repos(r):
                    path = git_data_path + repo["full_name"] + checkout_suffix
                    log.info("Mirroring repo %s (%s)", repo["name"], path)
                    mirror(repo["clone_url"], path)
                    with open(path + "cgitrc", "w") as f:
                        f.write(gh.repo_to_cgitrc(repo))

    def find_repos(path: str):
        for entry in os.scandir(path):
            if entry.is_dir():
                if is_bare_repo(entry.path):
                    clone(entry.path,
                          entry.path.replace(git_data_path,
                                             checkout_path))
                else:
                    find_repos(entry.path)

    if checkout_path:
        find_repos(git_data_path)


if __name__ == "__main__":
    main()
