import datetime
import os
import re
import time
from functools import lru_cache, wraps

from github import ContentFile, Github, Issue, Repository
from github.GithubException import (
    GithubException,
    RateLimitExceededException,
    UnknownObjectException,
)

token = os.environ.get("GITHUB_TOKEN")
github = Github(token)

exception_filenames = [
    ".data",
    ".git",
    ".github",
    "README.md",
    "Audit_Report.pdf",
    "comments.csv",
    ".gitkeep",
]


def github_retry_on_rate_limit(func):
    @wraps(func)
    def inner(*args, **kwargs):
        global github
        while True:
            try:
                return func(*args, **kwargs)
            except RateLimitExceededException:
                print("Rate Limit hit.")
                rl = github.get_rate_limit()
                time_to_sleep = int(
                    (rl.core.reset - datetime.datetime.utcnow()).total_seconds() + 1
                )
                print("Sleeping for %s seconds" % time_to_sleep)
                time.sleep(time_to_sleep)

    return inner


class IssueExtended(Issue.Issue):
    @classmethod
    def cast(cls, issue: Issue):
        issue.__class__ = IssueExtended

        for func in ["edit"]:
            setattr(issue, func, github_retry_on_rate_limit(getattr(issue, func)))
        return issue


class RepositoryExtended(Repository.Repository):
    @classmethod
    def cast(cls, repo: Repository.Repository):
        repo.__class__ = RepositoryExtended

        for func in [
            "create_issue",
            "get_contents",
            "get_issue",
            "get_labels",
            "create_label",
        ]:
            setattr(repo, func, github_retry_on_rate_limit(getattr(repo, func)))
        return repo


class ContentFileExtended(ContentFile.ContentFile):
    @classmethod
    def cast(cls, content_file: ContentFile):
        content_file.__class__ = ContentFileExtended

        for func in ["_completeIfNotSet"]:
            setattr(
                content_file,
                func,
                github_retry_on_rate_limit(getattr(content_file, func)),
            )
        return content_file


class GithubExtended(Github):
    @classmethod
    def cast(cls, github: Github):
        github.__class__ = GithubExtended

        for func in ["get_repo"]:
            setattr(github, func, github_retry_on_rate_limit(getattr(github, func)))
        return github


github = GithubExtended.cast(github)

# Issues list. Each issue is in the format:
# {
#   "id": 1,  # corresponds to the issue 001
#   "parent": 5,  # corresponds to the issue 005 => issue is duplicate of 005
#   "closed": True,  # True for a closed or duplicate issue
#   "auditor": "rcstanciu",
#   "severity": "H",  # Possible values: "H", "M" or "false"
#   "title": "Issue title",
#   "body": "Issue body",
#   "has_duplicates": True,
# }
issues = {}


def process_directory(repo, path):
    global issues

    print(f"[+] Processing directory /{path}")

    path_items = [
        x for x in repo.get_contents(path) if x.name not in exception_filenames
    ]
    dirs = [x for x in path_items if x.type == "dir"]
    files = [x for x in path_items if x.type != "dir"]

    # Root issues are closed by default
    closed = (
        True
        if path == ""
        else any(x in path.lower() for x in ["low", "false", "invalid"])
    )
    severity = "Invalid"

    if not closed:
        directory_severity = None

        try:
            directory_severity = (
                re.match(
                    r"^(H|M|High|Medium|GH|General-Health|GeneralHealth)-\d+$",
                    path,
                    re.IGNORECASE,
                )
                .group(1)
                .upper()
            )
        except Exception:
            pass

        if not directory_severity:
            try:
                directory_severity = (
                    re.match(
                        r"^\d+-(H|M|High|Medium|GH|General-Health|GeneralHealth)$",
                        path,
                        re.IGNORECASE,
                    )
                    .group(1)
                    .upper()
                )
            except Exception:
                pass

        if directory_severity:
            severity = directory_severity

    dir_issues_ids = []
    parent = None
    for index, file in enumerate(files):
        print(f"[-] Reading file {file.name}")
        last_file = index == len(files) - 1

        file = ContentFileExtended.cast(file)
        if "best" in file.name:
            issue_id = int(file.name.replace("-best.md", ""))
            parent = issue_id
        else:
            issue_id = int(file.name.replace(".md", ""))

        # We automatically set the parent in the following cases:
        # 1. The family has only one issue and no report has been selected.
        #    We select the only issue available as the report.
        # 2. The family is an invalid family (deduplicated inside the invalid folder) and no report is selected.
        #    We select the last processed issue in that family as the report.
        if not parent and (
            len(files) == 1
            or (
                severity == "Invalid"
                and path not in ["low", "false", "invalid"]
                and last_file
            )
        ):
            print(
                f"[!] Setting issue {issue_id} as the default parent of the current family /{path}"
            )
            parent = issue_id

        body = file.decoded_content.decode("utf-8")
        auditor = body.split("\n")[0]
        issue_title = re.match(r"^(?:[#\s]+)(.*)$", body.split("\n")[4]).group(1)
        title = f"{auditor} - {issue_title}"

        # Stop the script if an issue is found multiple times in the filesystem
        if issue_id in issues.keys():
            raise Exception("Issue %s found multiple times." % issue_id)

        issues[issue_id] = {
            "id": issue_id,
            "parent": None,
            "severity": severity,
            "body": body,
            "closed": closed,
            "auditor": auditor,
            "title": title,
            "has_duplicates": False,
        }
        dir_issues_ids.append(issue_id)

    # Set the parent field for all duplicates in this directory
    if parent is None and severity != "Invalid":
        raise Exception("Family %s does not have a primary file (-best.md)." % path)

    if parent:
        for issue_id in dir_issues_ids:
            if issue_id != parent:
                issues[parent]["has_duplicates"] = True
                issues[issue_id]["parent"] = parent
                issues[issue_id]["closed"] = True

    # Process any directories inside
    for directory in dirs:
        process_directory(repo, directory.path)


@lru_cache(maxsize=1024)
def get_github_issue(repo, issue_id):
    print("Fetching issue #%s" % issue_id)
    return IssueExtended.cast(repo.get_issue(issue_id))


def main():
    global issues
    global github

    repo = os.environ.get("GITHUB_REPOSITORY")
    repo = RepositoryExtended.cast(github.get_repo(repo))

    process_directory(repo, "")
    # Sort them by ID so we match the order
    # in which GitHub Issues created
    issues = dict(sorted(issues.items(), key=lambda item: item[1]["id"]))

    # Ensure issue IDs are sequential
    actual_issue_ids = list(issues.keys())
    expected_issue_ids = list(range(1, max(actual_issue_ids) + 1))
    missing_issue_ids = [x for x in expected_issue_ids if x not in actual_issue_ids]
    assert actual_issue_ids == expected_issue_ids, (
        "Expected issues %s actual issues %s. Missing %s"
        % (
            expected_issue_ids,
            actual_issue_ids,
            missing_issue_ids,
        )
    )

    # Sync issues
    for issue_id, issue in issues.items():
        print("Issue #%s" % issue_id)

        issue_labels = []
        if issue["has_duplicates"]:
            issue_labels.append("Has Duplicates")
        elif issue["parent"]:
            issue_labels.append("Duplicate")

        if not issue["closed"] or issue["parent"]:
            if issue["severity"] in ["H", "High"]:
                issue_labels.append("High")
            elif issue["severity"] in ["M", "Medium"]:
                issue_labels.append("Medium")
            elif issue["severity"] in ["GH", "General-Health", "GeneralHealth"]:
                issue_labels.append("General Health")

        if issue["closed"] and not issue["parent"]:
            issue_labels.append("Excluded")

        # Try creating/updating the issue until a success path is hit
        must_sleep = False
        while True:
            try:
                # Fetch existing issue
                gh_issue = get_github_issue(repo, issue_id)

                # We persist all labels except High/Medium/Has Duplicates/Duplicate
                existing_labels = [x.name for x in gh_issue.labels]
                new_labels = existing_labels.copy()
                if "High" in existing_labels:
                    new_labels.remove("High")
                if "Medium" in existing_labels:
                    new_labels.remove("Medium")
                if "General Health" in existing_labels:
                    new_labels.remove("General Health")
                if "Has Duplicates" in existing_labels:
                    new_labels.remove("Has Duplicates")
                if "Duplicate" in existing_labels:
                    new_labels.remove("Duplicate")
                if "Excluded" in existing_labels:
                    new_labels.remove("Excluded")
                new_labels = issue_labels + new_labels

                must_update = False
                if sorted(existing_labels) != sorted(new_labels):
                    must_update = True
                    print(
                        "\tLabels differ. Old: %s New: %s"
                        % (existing_labels, new_labels)
                    )

                if gh_issue.title != issue["title"]:
                    must_update = True
                    print(
                        "\tTitles differ: Old: %s New: %s"
                        % (gh_issue.title, issue["title"])
                    )

                expected_body = (
                    issue["body"]
                    if not issue["parent"]
                    else issue["body"] + f"\n\nDuplicate of #{issue['parent']}\n"
                )
                if expected_body != gh_issue.body:
                    must_update = True
                    print("\tBodies differ. See the issue edit history for the diff.")

                if must_update:
                    print("\tIssue needs to be updated.")
                    gh_issue.edit(
                        title=issue["title"],
                        body=issue["body"],
                        state="closed" if issue["closed"] else "open",
                        labels=new_labels,
                    )
                    # Exit the inifite loop and sleep
                    must_sleep = True
                    break
                else:
                    print("\tIssue does not need to be updated.")
                    # Exit the infinite loop and don't sleep
                    # since we did not make any edits
                    break
            except UnknownObjectException:
                print("\tCreating issue")
                # Create issue - 1 API call
                gh_issue = repo.create_issue(
                    issue["title"], body=issue["body"], labels=issue_labels
                )
                if issue["closed"]:
                    gh_issue.edit(state="closed")

                # Exit the infinite loop and sleep
                must_sleep = True
                break

        # Sleep between issues if any edits/creations have been made
        if must_sleep:
            print("\tSleeping for 1 second...")
            time.sleep(1)

    print("Referencing parent issue from duplicate issues")
    duplicate_issues = {k: v for k, v in issues.items() if v["parent"]}
    # Set duplicate label
    for issue_id, issue in duplicate_issues.items():
        # Try updating the issue until a success path is hit
        must_sleep = False
        while True:
            try:
                print(
                    "\tReferencing parent issue %s from duplicate issue %s."
                    % (issue["parent"], issue_id)
                )

                # Fetch existing issue
                gh_issue = get_github_issue(repo, issue_id)
                expected_body = issue["body"] + f"\n\nDuplicate of #{issue['parent']}\n"

                if expected_body != gh_issue.body:
                    gh_issue.edit(
                        body=issue["body"] + f"\n\nDuplicate of #{issue['parent']}\n",
                    )
                    must_sleep = True
                else:
                    print("\t\tIssue %s does not need to be updated." % issue_id)

                # Exit the inifinite loop
                break

            except GithubException as e:
                print(e)

                # Sleep for 5 minutes (in case secondary limits have been hit)
                # Don't exit the inifite loop and try again
                time.sleep(300)

        # Sleep between issue updates
        if must_sleep:
            print("\t\tSleeping for 1 second...")
            time.sleep(1)


if __name__ == "__main__":
    main()
