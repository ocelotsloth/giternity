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

from os.path import exists, join
from subprocess import run

from colors import color
import requests
import toml


__version__ = "0.4.0"


def mirror(url: str, path: str):
    if exists(path):
        run(["git", "-C", path, "remote", "update", "--prune"],
            stdout=subprocess.DEVNULL)
    else:
        run(["git", "clone", "--bare", "--mirror", url, path],
            stdout=subprocess.DEVNULL)

    web_dir = join(path, "info", "web")

    os.makedirs(web_dir, exist_ok=True)

    # set last modified date
    date = run(["git", "-C", path,
                "for-each-ref",
                "--sort=-authordate",
                "--count=1",
                "--format='%(authordate:iso8601)'"],
               stdout=subprocess.PIPE)

    with open(join(web_dir, "last-modified"), "wb") as f:
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
    def __init__(self, cgit_url=None, token=None):
        session = requests.Session()
        session.headers.update({
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "giternity ({})".format(__version__)
        })
        if token:
            session.headers.update({
                "Authorization": "token %s" % token,
            })
        self.s = session
        self.api = "https://api.github.com"
        self.cgit_url = cgit_url

    def get_repo(self, owner: str, repository: str):
        return self.s.get(self.api + "/repos/{}/{}".format(owner, repository))\
                     .json()

    def get_repos(self, user: str):
        # FIXME (arrdem 2018-07-01):
        #   while next_page ...
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


def find_repos(git_data_path: str, checkout_path: str):
    for entry in os.scandir(git_data_path):
        if entry.is_dir():
            if is_bare_repo(entry.git_data_path):
                clone(entry.git_data_path,
                      entry.git_data_path.replace(git_data_path,
                                                  checkout_path))
            else:
                find_repos(entry.git_data_path)


_LOG_LEVEL_STRINGS = ["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"]


def _log_level_string_to_int(log_level_string):
    if log_level_string not in _LOG_LEVEL_STRINGS:
        raise argparse.ArgumentTypeError(
          "invalid choice: {0} (choose from {1})"
          .format(log_level_string,
                  _LOG_LEVEL_STRINGS))

    log_level_int = getattr(log, log_level_string, log.INFO)

    return log_level_int


parser = argparse.ArgumentParser(
  description="Mirror git repositories and retrieve metadata for cgit.",
  epilog="Homepage: https://github.com/rahiel/giternity")

parser.add_argument("--version",
                    action="version",
                    version="%(prog)s {}".format(__version__))

parser.add_argument("--dry-run",
                    help="show a plan for archiving repositories and exit",
                    action="store_true",
                    dest="dry_run",
                    default=False)

parser.add_argument("-c", "--config",
                    help="configuration file for %(prog)s",
                    dest="config_file",
                    default="/etc/giternity.toml")

parser.add_argument("--log-level",
                    default="INFO",
                    dest="log_level",
                    type=_log_level_string_to_int,
                    nargs="?",
                    help=("Set the logging output level. {0}"
                          .format(_LOG_LEVEL_STRINGS)))


def main():
    args = parser.parse_args()

    log.basicConfig(level=args.log_level,
                    format='%(name)-12s: %(levelname)-8s %(message)s')

    try:
        config = toml.load(args.config_file)
    except FileNotFoundError:
        print(color("No configuration file found!", fg="red"))
        print("Please place your configuration at "
              + color(args.config_file, style="bold"))
        sys.exit(1)

    git_data_path = config.get("git_data_path", "/srv/git/")
    checkout_path = config.get("checkout_path")
    cgit_url = config.get("cgit_url")
    checkout_suffix = config.get("checkout_suffix", "")

    # The plan for what to archive and where it will go
    archive_plan = []

    gh_config = config.get("github")
    if gh_config:
        repos = gh_config.get("repositories", [])
        token = gh_config.get("token")
        gh_api = GitHub(cgit_url=cgit_url, token=token)

        # FIXME (arrdem 2018-06-20):
        #   Can this loop be cleaned up at all?
        for addr in repos:
            if "/" in addr:
                log.debug("Fetching repo %s", addr)
                path = join(git_data_path,
                            "{}{}".format(addr, checkout_suffix))
                owner, name = addr.split("/")
                url = "https://github.com/{}/{}.git".format(owner, name)
                repo = gh_api.get_repo(owner, name)
                metadata = gh_api.repo_to_cgitrc(repo)
                archive_plan.append((repo, metadata, url, path))

            else:
                log.debug("Fetching user/group %s", addr)
                for repo in gh_api.get_repos(addr):
                    path = join(git_data_path, "{}{}"
                                .format(repo["full_name"],
                                        checkout_suffix))
                    url = repo["clone_url"]
                    metadata = gh_api.repo_to_cgitrc(repo)
                    archive_plan.append((repo, metadata, url, path))
    else:
        gh_api = GitHub(cgit_url=cgit_url, token='')
    
    # Arbitrary git repositories
    arbitrary_repos = config.get("repos")
    if arbitrary_repos:
        for repo in arbitrary_repos:
            repo['full_name'] = '{}/{}'.format(repo['owner'], repo['name'])
            log.debug("Configuring repo %s", repo['full_name'])
            path = "{}{}{}".format(git_data_path, repo['full_name'], checkout_suffix)
            url = repo["clone_url"]
            metadata = gh_api.repo_to_cgitrc(repo)
            archive_plan.append((repo, metadata, url, path))

    if args.dry_run:
        for repo, metadata, url, path in archive_plan:
            print("""%s (%s) -> %s""" % (repo["full_name"], url, path))

    else:
        log.info("Mirroring repositories...")
        for repo, metadata, url, path in archive_plan:
            mirror(url, path)
            # FIXME (arrdem 2018-07-01):
            #   Slurp existing cgitrc and merge with it?
            with open(join(path, "cgitrc"), "w") as f:
                f.write(metadata)

        if checkout_path:
            log.info("Checking out repositories to %s" % checkout_path)
            find_repos(git_data_path, checkout_path)


if __name__ == "__main__":
    main()
