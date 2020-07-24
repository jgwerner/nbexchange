import datetime
import glob
import re
from collections import Sequence, defaultdict

import nbgrader.exchange.abc as abc
import os
import requests

from dateutil.tz import gettz
from functools import partial
from nbgrader.exchange import ExchangeError
from nbgrader.utils import full_split
from traitlets import Unicode, Bool, Instance
from urllib.parse import urljoin


def contains_format(string):
    """
    Checks if a string has format markers
    :param string: the string to check
    :return: true if the string contains any {format} markers.
    """
    return re.search("([^{]|^){[^}]+}", string) is not None


def format_keys(string):
    """
    Find all format keys in a format string
    :param string: the string to look in
    :return: all format keys found in the format string
    """
    return [x.group(2) for x in re.finditer("([^{]|^){([^}]+)}", string)]


def maybe_format(string, **values):
    """
    This function applies all formats to a string that are available, leaving all other format strings in.

    :param string: the string to format
    :param values: the kwargs representing the values to format the string with
    :return: partially formatted string
    """
    try:
        formats = format_keys(string)
        return string.format(
            **{
                **{x: f"{{{x}}}" for x in formats if x not in values},
                **{x: y for x, y in values.items()},
            }
        )
    except KeyError:
        return string


class Exchange(abc.Exchange):
    path_includes_course = Bool(
        False,
        help="""
Whether the path for fetching/submitting  assignments should be
prefixed with the course name. If this is `False`, then the path
will be something like `./ps1`. If this is `True`, then the path
will be something like `./course123/ps1`.
""",
    ).tag(config=True)

    assignment_dir = Unicode(
        ".",
        help="""
Local path for storing student assignments.  Defaults to '.'
which is normally Jupyter's notebook_dir.
""",
    ).tag(config=True)

    base_service_url = Unicode(
        os.environ.get("NAAS_BASE_URL", "https://noteable.edina.ac.uk")
    ).tag(config=True)

    def service_url(self):
        this_url = urljoin(self.base_service_url, "/services/nbexchange/")
        self.log.debug(f"service_url: {this_url}")
        return this_url

    course_id = Unicode(os.environ.get("NAAS_COURSE_ID", "no_course")).tag(config=True)

    def fail(self, msg):
        self.log.fatal(msg)
        raise ExchangeError(msg)

    def set_timestamp(self):
        """Set the timestap using the configured timezone."""
        tz = gettz(self.timezone)
        if tz is None:
            self.fail("Invalid timezone: {}".format(self.timezone))
        self.timestamp = datetime.datetime.now(tz).strftime(self.timestamp_format)

    def api_request(self, path, method="GET", *args, **kwargs):

        jwt_token = os.environ.get("NAAS_JWT")

        cookies = dict()
        headers = dict()

        if jwt_token:
            cookies["noteable_auth"] = jwt_token

        url = self.service_url() + path

        self.log.info(f"Exchange.api_request calling exchange with url {url}")

        if method == "GET":
            get_req = partial(requests.get, url, headers=headers, cookies=cookies)
            self.log.info(f"Exchange.api_request GET returning {get_req}")
            return get_req(*args, **kwargs)
        elif method == "POST":
            post_req = partial(requests.post, url, headers=headers, cookies=cookies)
            return post_req(*args, **kwargs)
        elif method == "DELETE":
            delete_req = partial(requests.delete, url, headers=headers, cookies=cookies)
            return delete_req(*args, **kwargs)
        else:
            raise NotImplementedError(f"HTTP Method {method} is not implemented")

    def construct_course_dir(self, nbgrader_step, student_id, assignment_id):
        """
        Construct the path to a particular assignment directory in the course directory. Not that this is only
        to be used for creating paths when the student and assignment is known.

        :param nbgrader_step: Which step to construct for (submitted, released, source, ...)
        :param student_id: The student id that we create the path for
        :param assignment_id: The assignment we create the path for
        :return: the full path to a assignment in the course directory
        """
        structure = os.path.join(
            self.coursedir.root, self.coursedir.directory_structure
        )
        return os.path.join(
            *[
                x.format(
                    nbgrader_step=nbgrader_step,
                    student_id=student_id,
                    assignment_id=assignment_id,
                )
                for x in full_split(structure)
            ]
        )

    def construct_assignment_dir(self, assignment_id, course_id=None, subdir=None):
        """
        Construct a path to a particular assignment in the assignment directory.
        Takes an optional course_id that is only used if path_includes_course is specified (in which case the course_id is required).
        It also takes an optional subdir, to allow the construction of paths to the feedback directory of an
        assignment directory.

        :param assignment_id: The assignment id to construct a path for
        :param course_id: The course_id to use (sometimes optional)
        :param subdir: The sub directory to use (optional)
        :return: the full path to an assignment (or subdirectory) in the assignment directory
        """
        structure = self.assignment_dir
        if self.path_includes_course:
            if course_id is None:
                self.log.info(
                    "Trying to get directory structure that includes course id without specifying course id"
                )
                return
            structure = os.path.join(structure, course_id)
        structure = os.path.join(structure, assignment_id)
        if subdir is not None:
            structure = os.path.join(structure, subdir)
        return structure

    def get_course_dir(self, nbgrader_step, student_id=None, assignment_id=None):
        """
        Returns all assignments for specific student/all students, for a specific assignment/all assignments in
        the course directory.

        The assignments are returns as a list of dicts, where the dicts have the keys 'files' containing a
        list of all files found for that assignment, 'root' containing the path to the parent folder of the files,
        and the key 'details', which contains the details for
        that assignment (that is, the student_id, and assignment_id, unless those are specified in the call
        to the method).

        :param nbgrader_step: Which step to construct for (submitted, released, source, ...)
        :param student_id: The student to look for (or None for all)
        :param assignment_id: The assignment to look for (or None for all)
        :return: All assignments matching the criteria.
        """
        structure = os.path.join(
            self.coursedir.root, self.coursedir.directory_structure
        )
        kwargs = {"nbgrader_step": nbgrader_step}
        if assignment_id is not None:
            kwargs["assignment_id"] = assignment_id
        if student_id is not None:
            kwargs["student_id"] = student_id

        return self.get_files(self.get_directory_structure(structure, **kwargs))

    def get_assignment_dir(self, course_id=None, assignment_id=None, subdir=None):
        """
        Get all the assignments in an assignment directory.

        The assignments are returns as a list of dicts, where the dicts have the keys 'files' containing a
        list of all files found for that assignment, 'root' containing the path to the parent folder of the files,
        and the key 'details', which contains the details for
        that assignment (that is, the course_id, and assignment_id, unless those are specified in the call
        to the method).

        :param course_id: The course to look in (if path_includes_course is specified)
        :param assignment_id: The assignment to look for, or None for all assignments
        :param subdir: Optional subdirectory to look in.
        :return: All assignments matching the criteria.
        """
        structure = self.assignment_dir
        if self.path_includes_course:
            structure = os.path.join(structure, "{course_id}")
        structure = os.path.join(structure, "{assignment_id}")
        if subdir is not None:
            structure = os.path.join(structure, subdir)
        kwargs = {}
        if assignment_id is not None:
            kwargs["assignment_id"] = assignment_id
        if course_id is not None:
            kwargs["course_id"] = course_id
        return self.get_files(self.get_directory_structure(structure, **kwargs))

    def get_directory_structure(self, directory_structure, **kwargs):
        """
        A helper method that returns all files found in a particular directory structure. The directory structure
        can contain {format} specifiers, to indicate that multiple folders can match at that point. If the
        format specifiers are not specified in the kwargs, then multiple folders will be returned, otherwise
        the one specified in kwargs will be used.

        The files are returns as a list of dicts, where the dicts have the keys 'files' containing a
        list of all files found in a specific path, 'root' containing the path to the parent folder of the files,
        and the key 'details', which contains the details for
        those files (that is, any format keys that are not in kwargs will be passed back here).

        :param directory_structure: The directory structure
        :param kwargs: optional specifiers for which folders to look in.
        :return: All files matching criteria
        """
        structure = full_split(directory_structure)
        full_structure = []

        for part in structure:
            the_part = maybe_format(part, **kwargs)
            if (
                len(full_structure) > 0
                and not contains_format(the_part)
                and not contains_format(full_structure[-1])
            ):
                full_structure[-1] = os.path.join(full_structure[-1], the_part)
            else:
                full_structure.append(the_part)
        return full_structure

    def group_by(self, key, entries):
        """
        Convenience method that groups a list of dicts by one of the keys in the dicts. If the key does not
        exist, the dict is ignored. Returns a dict, where each entry is a value of dict[key] -> list of dict with
        matching key->value pair.

        :param key: The key to group by
        :param entries: the list of dicts to group
        :return: dict[str, list[dict]]
        """
        ordered = defaultdict(list)
        for item in entries:
            if key in item.get("details", {}):
                ordered[item["details"][key]].append(item)
        return ordered

    def get_files(self, root, structure=None, **kwargs):
        """
        Return all the files in the root directory that matches the structure, where the structure is a list of
        sub directories (as returned by the full_split function).

        The files are returns as a list of dicts, where the dicts have the keys 'files' containing a
        list of all files found in a specific path, 'root' containing the path to the parent folder of the files,
        and the key 'details', which contains the details for
        those files (that is, any format keys that are not in kwargs will be passed back here).

        :param root: The root path to look in
        :param structure: The structure as a list
        :param kwargs: specifiers
        :return: list of dicts for each folder found
        """
        if structure is None:
            structure = []

        if isinstance(root, list):
            return self.get_files(root[0], root[1:] + structure, **kwargs)

        if len(structure) == 0:
            if os.path.isdir(root):
                files = os.listdir(root)
                return [
                    {
                        "files": [os.path.join(root, f) for f in files],
                        "root": root,
                        "details": kwargs,
                    }
                ]
            else:
                return []

        if not contains_format(structure[0]):
            root = os.path.join(root, structure[0])
            return self.get_files(root, structure[1:], **kwargs)
        files = []
        # TODO: should we return error objects when files are missing?
        if os.path.exists(root):
            for filename in os.listdir(root):
                new_root = os.path.join(root, filename)
                detail_name = structure[0].strip("{}")
                kwargs[detail_name] = filename
                if os.path.isdir(new_root):
                    files.extend(self.get_files(new_root, structure[1:], **kwargs))
        else:
            self.log.info(f"'{root}' does not exist while trying to find files")
            return []
        return files

    def get_local_assignments(self, assignments, course_id=None):
        """
        Returns a users local assignments.

        :param assignments: A list of all possible assignments.
                            This is needed to avoid having to guess what is and isn't an assignment.
        :param course_id: Course id, if path_includes_course is specified
        :return:
        """
        found_assignments = []
        for assign in assignments:
            found_assignments.extend(
                [
                    {
                        "details": {"assignment_id": assign, **x["details"]},
                        "files": x["files"],
                    }
                    for x in self.get_files(
                        self.get_assignment_dir(
                            course_id=course_id, assignment_id=assign
                        )
                    )
                ]
            )
        return found_assignments

    def get_all_local_assignments(self, assignments, student_id=None, course_id=None):
        """
        Returns all local assignments, including all the ones found in the course directory.

        :param assignments: A list of all possible assignments.
                            This is needed to avoid having to guess what is and isn't an assignment.
        :param student_id: The student id, for assignments in the course directory
        :param course_id: Course id, if path_includes_course is specified
        :return:
        """
        found_assignments = []
        for assign in assignments:
            found_assignments.extend(
                [
                    {
                        "details": {
                            "assignment_id": assign,
                            "status": "fetched",
                            **x["details"],
                        },
                        "files": x["files"],
                    }
                    for x in self.get_assignment_dir(
                        course_id=course_id, assignment_id=assign
                    )
                ]
            )
        found_assignments.extend(
            [
                {
                    "details": {"status": "submitted", **x["details"]},
                    "files": x["files"],
                }
                for x in self.get_local_submissions(student_id=student_id)
            ]
        )
        found_assignments.extend(
            [
                {"details": {"status": "released", **x["details"]}, "files": x["files"]}
                for x in self.get_local_release(student_id=student_id)
            ]
        )
        found_assignments.extend(
            [
                {
                    "details": {"status": "autograded", **x["details"]},
                    "files": x["files"],
                }
                for x in self.get_local_autograded(student_id=student_id)
            ]
        )
        found_assignments.extend(
            [
                {"details": {"status": "source", **x["details"]}, "files": x["files"]}
                for x in self.get_local_source(student_id=student_id)
            ]
        )
        return found_assignments

    def get_local_submissions(self, student_id=None, assignment_id=None):
        """
        Returns all the submissions on the local notebook.

        :param student_id: The student to look for, or None for all students
        :param assignment_id: The assignment to look for, or None for all assignments
        :return:
        """
        return self.get_course_dir(
            self.coursedir.submitted_directory,
            student_id=student_id,
            assignment_id=assignment_id,
        )

    def get_local_feedback(self, student_id=None, assignment_id=None):
        """
        Returns all the feedback on the local notebook.

        :param student_id: The student to look for, or None for all students
        :param assignment_id: The assignment to look for, or None for all assignments
        :return:
        """
        return self.get_course_dir(
            self.coursedir.feedback_directory,
            student_id=student_id,
            assignment_id=assignment_id,
        )

    def get_local_autograded(self, student_id=None, assignment_id=None):
        """
        Returns all the autograded assignments on the local notebook.

        :param student_id: The student to look for, or None for all students
        :param assignment_id: The assignment to look for, or None for all assignments
        :return:
        """
        return self.get_course_dir(
            self.coursedir.autograded_directory,
            student_id=student_id,
            assignment_id=assignment_id,
        )

    def get_local_release(self, student_id=None, assignment_id=None):
        """
        Returns all the released assignments on the local notebook.

        :param student_id: The student to look for, or None for all students
        :param assignment_id: The assignment to look for, or None for all assignments
        :return:
        """
        return self.get_course_dir(
            self.coursedir.release_directory,
            student_id=student_id,
            assignment_id=assignment_id,
        )

    def get_local_source(self, student_id=None, assignment_id=None):
        """
        Returns all the sources on the local notebook.

        :param student_id: The student to look for, or None for all students
        :param assignment_id: The assignment to look for, or None for all assignments
        :return:
        """
        return self.get_course_dir(
            self.coursedir.source_directory,
            student_id=student_id,
            assignment_id=assignment_id,
        )

    def get_local_assignments_paths(self, assignments, course_id=None):
        """
        Returns all folder paths for all the assignments on the local notebook.

        :param student_id: The student to look for, or None for all students
        :param assignment_id: The assignment to look for, or None for all assignments
        :return:
        """
        found_assignments = []
        for assign in assignments:
            found_assignments.extend(
                [
                    x["root"]
                    for x in self.get_files(
                        self.get_assignment_dir(
                            course_id=course_id, assignment_id=assign
                        )
                    )
                ]
            )
        return found_assignments

    def get_local_submissions_paths(self, student_id=None, assignment_id=None):
        """
        Returns all the paths for all submissions on the local notebook.

        :param student_id: The student to look for, or None for all students
        :param assignment_id: The assignment to look for, or None for all assignments
        :return:
        """
        return [
            x["root"]
            for x in self.get_course_dir(
                self.coursedir.submitted_directory,
                student_id=student_id,
                assignment_id=assignment_id,
            )
        ]

    def get_local_feedback_paths(self, student_id=None, assignment_id=None):
        """
        Returns all the paths for all feedbacks on the local notebook.

        :param student_id: The student to look for, or None for all students
        :param assignment_id: The assignment to look for, or None for all assignments
        :return:
        """
        return [
            x["root"]
            for x in self.get_course_dir(
                self.coursedir.feedback_directory,
                student_id=student_id,
                assignment_id=assignment_id,
            )
        ]

    def get_local_autograded_paths(self, student_id=None, assignment_id=None):
        """
        Returns all the paths for all autograded assignments on the local notebook.

        :param student_id: The student to look for, or None for all students
        :param assignment_id: The assignment to look for, or None for all assignments
        :return:
        """
        return [
            x["root"]
            for x in self.get_course_dir(
                self.coursedir.autograded_directory,
                student_id=student_id,
                assignment_id=assignment_id,
            )
        ]

    def get_local_release_paths(self, student_id=None, assignment_id=None):
        """
        Returns all the paths for all released assignments on the local notebook.

        :param student_id: The student to look for, or None for all students
        :param assignment_id: The assignment to look for, or None for all assignments
        :return:
        """
        return [
            x["root"]
            for x in self.get_course_dir(
                self.coursedir.release_directory,
                student_id=student_id,
                assignment_id=assignment_id,
            )
        ]

    def get_local_source_paths(self, student_id=None, assignment_id=None):
        """
        Returns all the paths for all sources on the local notebook.

        :param student_id: The student to look for, or None for all students
        :param assignment_id: The assignment to look for, or None for all assignments
        :return:
        """
        return [
            x["root"]
            for x in self.get_course_dir(
                self.coursedir.source_directory,
                student_id=student_id,
                assignment_id=assignment_id,
            )
        ]

    def save_local_assignments(self, course_id, assignment_id, assignment):
        """
        Not yet implemented method for saving assignments to the local notebook

        :param course_id: The course to save for
        :param assignment_id: The assignment id to save to
        :param assignment: The assignment to save
        :return:
        """

    def save_local_submission(self, student_id, course_id, assignment_id, submission):
        """
        Not yet implemented method for saving submission to the local notebook

        :param student_id: The student to save for
        :param course_id: The course to save for
        :param assignment_id: The assignment id to save to
        :param submission: The assignment to save
        :return:
        """

    def save_local_feedback(self, student_id, course_id, assignment_id, feedback):
        """
        Not yet implemented method for saving feedback to the local notebook

        :param student_id: The student to save for
        :param course_id: The course to save for
        :param assignment_id: The assignment id to save to
        :param feedback: The assignment to save
        :return:
        """

    def init_src(self):
        """Compute and check the source paths for the transfer."""
        raise NotImplementedError

    def init_dest(self):
        """Compute and check the destination paths for the transfer."""
        raise NotImplementedError

    def copy_files(self):
        """Actually do the file transfer."""
        raise NotImplementedError

    def do_copy(self, src, dest):
        """Copy the src dir to the dest dir omitting the self.coursedir.ignore globs."""
        raise NotImplementedError

    def start(self):
        self.log.info(f"Called start on {self.__class__.__name__}")

        self.init_src()
        self.init_dest()
        self.copy_files()

    def _assignment_not_found(self, src_path, other_path):
        msg = f"Assignment not found at: {src_path}"
        self.log.fatal(msg)
        found = glob.glob(other_path)
        if found:
            # Normally it is a bad idea to put imports in the middle of
            # a function, but we do this here because otherwise fuzzywuzzy
            # prints an annoying message about python-Levenshtein every
            # time nbgrader is run.
            from fuzzywuzzy import fuzz

            scores = sorted([(fuzz.ratio(self.src_path, x), x) for x in found])
            self.log.error("Did you mean: %s", scores[-1][1])

        raise ExchangeError(msg)
