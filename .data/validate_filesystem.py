import os
import re
import csv

total_issues = None
comment_filename = "comments.csv"
exception_filenames = [
    ".data",
    ".git",
    ".github",
    "README.md",
    "Audit_Report.pdf",
    ".gitkeep",
    ".gitignore",
    comment_filename,
]


def consume_comment_file():
    with open(comment_filename) as f:
        try:
            reader = csv.DictReader(f)
        except Exception:
            return ["Unable to consume %s" % comment_filename]

        if not reader.fieldnames or reader.fieldnames != ["issue_number", "comment"]:
            return ["Incorrect csv header, expected `issue_number,comment`"]

        errors = []
        for row in reader:
            try:
                issue_number = int(re.match(r"(\d+)", row["issue_number"]).group(0))
            except Exception:
                errors.append("Unable to extract issue number from %s" % row)
                continue
            if issue_number < 1 or issue_number > total_issues:
                errors.append("Issue %s should not be in csv" % issue_number)

            comment = row.get("comment")
            if not comment or len(comment) == 0:
                errors.append("Empty comment on issue %s in the csv" % issue_number)
        return errors


def main():
    global total_issues

    try:
        total_issues = int(os.environ.get("TOTAL_ISSUES"))
    except:
        print("TOTAL_ISSUES secret not set.")
        return

    # Store all the errors found
    errors = []
    # Store all the issues read
    issues = []

    def process_directory(path):
        nonlocal issues
        print("Directory %s" % path)

        # Get the items in the directory
        items = [x for x in os.listdir(path) if x not in exception_filenames]

        directory_has_report = False
        for item in items:
            print("- Item %s" % item)
            is_dir = os.path.isdir(os.path.join(path, item))

            if is_dir:
                matches = [
                    r"^(H|M|High|Medium|GH|General-Health|GeneralHealth)-\d+$",
                    r"^\d+-(H|M|High|Medium|GH|General-Health|GeneralHealth)$",
                    r"^false$",
                    r"^invalid$",
                ]
                correctly_formatted = any(
                    re.match(pattern, item, re.IGNORECASE) for pattern in matches
                )
                if (
                    not any([x in path for x in ["invalid", "false"]])
                    and not correctly_formatted
                ):
                    errors.append("Directory %s is not formatted properly." % item)
                else:
                    process_directory(os.path.join(path, item))
            else:
                if not re.match(r"^\d+(-best)?.md$", item):
                    errors.append("File %s is not formatted properly." % item)
                    continue

                # Check if the file is the best report
                if "-best" in item:
                    if not directory_has_report:
                        directory_has_report = True
                    else:
                        errors.append(
                            "Directory %s has multiple best reports marked." % path
                        )

                # Extract issue number from the file name
                issue_number = int(re.match(r"(\d+)", item).group(0))

                # Check if the issue was already found
                if issue_number in issues:
                    errors.append("Issue %s exists multiple times." % issue_number)
                else:
                    issues.append(issue_number)

        if (
            path != "."
            and not any(x in path for x in ["invalid", "false"])
            and not directory_has_report
            and len(items) > 1
        ):
            errors.append("Directory %s does not have a best report selected." % path)

    # Start processing from the root
    process_directory(".")

    expected_issues = [x + 1 for x in range(total_issues)]
    # Check if all issues are found in the repo
    for x in expected_issues:
        if x not in issues:
            errors.append("Issue %s not found in the repo." % x)
    # Check if there are no additional issues added
    for x in issues:
        if x not in expected_issues:
            errors.append("Issue %s should not be in the repo." % x)

    if os.path.exists(comment_filename):
        errors.extend(consume_comment_file())

    if len(errors) > 0:
        for error in errors:
            print("❌ %s" % error)
        exit(1)

    print("✅ Repo structure is valid.")


if __name__ == "__main__":
    main()
