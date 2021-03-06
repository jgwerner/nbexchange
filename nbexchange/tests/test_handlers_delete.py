import logging
import sys

import pytest
from mock import patch

from nbexchange.handlers.base import BaseHandler
from nbexchange.tests.utils import (
    async_requests,
    clear_database,
    get_files_dict,
    user_kiz_instructor,
    user_kiz_student,
    user_zik_student,
)

logger = logging.getLogger(__file__)
logger.setLevel(logging.ERROR)

#################################
#
# Very Important Note
#
# The `clear_database` fixture removed all database records.
# In this suite of tests, we do that FOR EVERY TEST
# This means that every single test is run in isolation, and therefore will need to have the full Release, Fetch,
#   Submit steps done before the collection can be tested.
# (On the plus side, adding or changing a test will no longer affect those below)
#
#################################

##### DELETE /assignment (delete or purge assignment) ######

# require authenticated user (404 because the bounce to login fails)
@pytest.mark.gen_test
def test_delete_needs_user(app):
    with patch.object(BaseHandler, "get_current_user", return_value={}):
        r = yield async_requests.delete(app.url + "/assignment")
    assert r.status_code == 403  # why not 404???


# set up the file to be uploaded
files = get_files_dict(sys.argv[0])  # ourself :)

# Requires both params (none)
@pytest.mark.gen_test
def test_delete_needs_both_params(app, clear_database):
    with patch.object(
        BaseHandler, "get_current_user", return_value=user_kiz_instructor
    ):
        r = yield async_requests.delete(app.url + "/assignment")
    response_data = r.json()
    assert response_data["success"] == False
    assert (
        response_data["note"]
        == "Unreleasing an Assigment requires a course code and an assignment code"
    )


# Requires both params (just course)
@pytest.mark.gen_test
def test_delete_needs_assignment(app, clear_database):
    with patch.object(
        BaseHandler, "get_current_user", return_value=user_kiz_instructor
    ):
        r = yield async_requests.delete(app.url + "/assignment?course_id=course_a")
    assert r.status_code == 200
    response_data = r.json()
    assert response_data["success"] == False
    assert (
        response_data["note"]
        == "Unreleasing an Assigment requires a course code and an assignment code"
    )


# Requires both params (just assignment)
@pytest.mark.gen_test
def test_delete_needs_course(app, clear_database):
    with patch.object(
        BaseHandler, "get_current_user", return_value=user_kiz_instructor
    ):
        r = yield async_requests.delete(app.url + "/assignment?assignment_id=assign_a")
    assert r.status_code == 200
    response_data = r.json()
    assert response_data["success"] == False
    assert (
        response_data["note"]
        == "Unreleasing an Assigment requires a course code and an assignment code"
    )


# Student cannot release
# Note we have to use a user who's NEVER been an instructor on the course
@pytest.mark.gen_test
def test_delete_student_blocked(app, clear_database):
    with patch.object(BaseHandler, "get_current_user", return_value=user_zik_student):
        r = yield async_requests.get(app.url + "/assignments?course_id=course_2")
        r = yield async_requests.delete(
            app.url + "/assignment?course_id=course_2&assignment_id=assign_a"
        )
    assert r.status_code == 200
    response_data = r.json()
    assert response_data["success"] == False
    assert response_data["note"] == "User not an instructor to course course_2"


# Instructor, wrong course, cannot release
@pytest.mark.gen_test
def test_delete_wrong_course_blocked(app, clear_database):
    with patch.object(
        BaseHandler, "get_current_user", return_value=user_kiz_instructor
    ):
        r = yield async_requests.delete(
            app.url + "/assignment?course_id=course_1&assignment_id=assign_a"
        )
    assert r.status_code == 200
    response_data = r.json()
    assert response_data["success"] == False
    assert response_data["note"] == "User not subscribed to course course_1"


# instructor can delete
@pytest.mark.gen_test
def test_delete_instructor_delete(app, clear_database):
    with patch.object(
        BaseHandler, "get_current_user", return_value=user_kiz_instructor
    ):
        r = yield async_requests.post(
            app.url + "/assignment?course_id=course_2&assignment_id=assign_a",
            files=files,
        )
        r = yield async_requests.delete(
            app.url + "/assignment?course_id=course_2&assignment_id=assign_a",
            files=files,
        )
    assert r.status_code == 200
    response_data = r.json()
    assert response_data["success"] == True
    assert (
        response_data["note"]
        == "Assignment 'assign_a' on course 'course_2' marked as unreleased"
    )


# instructor can purge
@pytest.mark.gen_test
def test_delete_instructor_purge(app, clear_database):
    with patch.object(
        BaseHandler, "get_current_user", return_value=user_kiz_instructor
    ):
        r = yield async_requests.post(
            app.url + "/assignment?course_id=course_2&assignment_id=assign_b",
            files=files,
        )
        r = yield async_requests.delete(
            app.url
            + "/assignment?course_id=course_2&assignment_id=assign_b&purge=True",
            files=files,
        )
    assert r.status_code == 200
    response_data = r.json()
    assert response_data["success"] == True
    assert (
        response_data["note"]
        == "Assignment 'assign_b' on course 'course_2' deleted and purged from the database"
    )


# Instructor, wrong course, cannot delete
@pytest.mark.gen_test
def test_delete_wrong_course_blocked(app, clear_database):
    with patch.object(
        BaseHandler, "get_current_user", return_value=user_kiz_instructor
    ):
        r = yield async_requests.post(
            app.url + "/assignment?course_id=course_2&assignment_id=assign_a"
        )
        r = yield async_requests.delete(
            app.url + "/assignment?course_id=course_1&assignment_id=assign_a",
            files=files,
        )
    assert r.status_code == 200
    response_data = r.json()
    assert response_data["success"] == False
    assert response_data["note"] == "User not subscribed to course course_1"


# instructor releasing - Picks up the first attribute if more than 1 (wrong course)
@pytest.mark.gen_test
def test_delete_multiple_courses_listed_first_wrong_blocked(app, clear_database):
    with patch.object(
        BaseHandler, "get_current_user", return_value=user_kiz_instructor
    ):
        r = yield async_requests.post(
            app.url + "/assignment?course_id=course_2&assignment_id=assign_a",
            files=files,
        )
        r = yield async_requests.delete(
            app.url
            + "/assignment?course_id=course_1&course_id=course_2&assignment_id=assign_a",
            files=files,
        )
    assert r.status_code == 200
    response_data = r.json()
    assert response_data["success"] == False
    assert response_data["note"] == "User not subscribed to course course_1"


# instructor releasing - Picks up the first attribute if more than 1 (wrong course)
@pytest.mark.gen_test
def test_delete_multiple_courses_listed_first_right_passes(app, clear_database):
    with patch.object(
        BaseHandler, "get_current_user", return_value=user_kiz_instructor
    ):
        r = yield async_requests.post(
            app.url + "/assignment?course_id=course_2&assignment_id=assign_a",
            files=files,
        )
        r = yield async_requests.delete(
            app.url
            + "/assignment?course_id=course_2&course_id=course_1&assignment_id=assign_a",
            files=files,
        )
    assert r.status_code == 200
    response_data = r.json()
    assert response_data["success"] == True
    assert (
        response_data["note"]
        == "Assignment 'assign_a' on course 'course_2' marked as unreleased"
    )


# confirm unreleased does not show in list
@pytest.mark.gen_test
def test_delete_assignment10(app, clear_database):
    with patch.object(
        BaseHandler, "get_current_user", return_value=user_kiz_instructor
    ):
        r = yield async_requests.post(
            app.url + "/assignment?course_id=course_2&assignment_id=assign_a",
            files=files,
        )
        r = yield async_requests.delete(
            app.url + "/assignment?course_id=course_2&assignment_id=assign_a",
            files=files,
        )
        r = yield async_requests.get(app.url + "/assignments?course_id=course_2")
    assert r.status_code == 200
    response_data = r.json()
    assert response_data["success"] == True
    assert "note" not in response_data  # just that it's missing
    assert len(response_data["value"]) == 0
