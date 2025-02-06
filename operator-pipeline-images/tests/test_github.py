from typing import Any, List
from unittest.mock import ANY, MagicMock, call, patch

import pytest
from operatorcert import github
from requests import HTTPError, Response


def test_get_session_github_token(monkeypatch: Any) -> None:
    monkeypatch.setenv("GITHUB_TOKEN", "123")
    session = github._get_session(auth_required=True)

    assert session.headers["Authorization"] == "Bearer 123"


def test_get_session_no_auth() -> None:
    session = github._get_session(auth_required=False)
    assert "Authorization" not in session.headers


def test_get_session_missing_token() -> None:
    with pytest.raises(Exception):
        github._get_session(auth_required=True)


@patch("operatorcert.github._get_session")
def test_get(mock_session: MagicMock) -> None:
    mock_session.return_value.get.return_value.json.return_value = {"key": "val"}
    resp = github.get("https://foo.com/v1/bar", {})
    assert resp == {"key": "val"}


@patch("operatorcert.github._get_session")
def test_get_with_error(mock_session: MagicMock) -> None:
    response = Response()
    response.status_code = 500
    mock_session.return_value.get.return_value.raise_for_status.side_effect = HTTPError(
        response=response
    )
    with pytest.raises(HTTPError):
        github.get("https://foo.com/v1/bar", {})


@patch("operatorcert.github._get_session")
def test_post(mock_session: MagicMock) -> None:
    mock_session.return_value.post.return_value.json.return_value = {"key": "val"}
    resp = github.post("https://foo.com/v1/bar", {})

    assert resp == {"key": "val"}


@patch("operatorcert.github._get_session")
def test_post_with_error(mock_session: MagicMock) -> None:
    response = Response()
    response.status_code = 400
    mock_session.return_value.post.return_value.raise_for_status.side_effect = (
        HTTPError(response=response)
    )
    with pytest.raises(HTTPError):
        github.post("https://foo.com/v1/bar", {})


@patch("operatorcert.github._get_session")
def test_patch(mock_session: MagicMock) -> None:
    mock_session.return_value.patch.return_value.json.return_value = {"key": "val"}
    resp = github.patch("https://foo.com/v1/bar", {})

    assert resp == {"key": "val"}


@patch("operatorcert.github._get_session")
def test_patch_with_error(mock_session: MagicMock) -> None:
    response = Response()
    response.status_code = 400
    mock_session.return_value.patch.return_value.raise_for_status.side_effect = (
        HTTPError(response=response)
    )
    with pytest.raises(HTTPError):
        github.patch("https://foo.com/v1/bar", {})


@pytest.mark.parametrize(
    "current_labels, add_label, remove_label, remove_namespaced, expected_add, expected_remove",
    [
        pytest.param([], ["label1"], [], False, ["label1"], [], id="add label"),
        pytest.param(
            ["label1"], ["label1"], [], False, [], [], id="add existing label"
        ),
        pytest.param(
            ["label1"], [], ["label1"], False, [], ["label1"], id="remove label"
        ),
        pytest.param([], [], ["label1"], False, [], [], id="remove non-existing label"),
        pytest.param(
            ["namespace/label1", "namespace/label2", "existing_label", "bar"],
            ["namespace/new"],
            [],
            False,
            ["namespace/new"],
            [],
            id="add namespaced label",
        ),
        pytest.param(
            ["namespace/label1", "namespace/label2", "existing_label", "bar"],
            ["namespace/new"],
            [],
            True,
            ["namespace/new"],
            ["namespace/label2", "namespace/label1"],
            id="add namespaced label and remove existing",
        ),
        pytest.param(
            ["namespace/label1", "namespace/label2", "existing_label", "bar"],
            ["namespace/label1"],
            [],
            True,
            [],
            ["namespace/label2"],
            id="remove namespaced label and keep existing",
        ),
        pytest.param(
            ["namespace/label1", "namespace/label2", "existing_label", "bar"],
            ["namespace/new"],
            ["bar"],
            True,
            ["namespace/new"],
            ["bar", "namespace/label2", "namespace/label1"],
            id="add namespaced label and remove existing and non-namespaced",
        ),
    ],
)
@patch("operatorcert.github.remove_labels_from_pull_request")
@patch("operatorcert.github.add_labels_to_pull_request")
def test_add_or_remove_labels(
    mock_add_label: MagicMock,
    mock_remove_label: MagicMock,
    current_labels: List[Any],
    add_label: List[str],
    remove_label: List[str],
    remove_namespaced: bool,
    expected_add: List[str],
    expected_remove: List[str],
) -> None:
    mock_github = MagicMock()

    mock_current_labels = []
    for label in current_labels:
        # The name property can't be set directly on the MagicMock
        mock_label = MagicMock()
        mock_label.name = label
        mock_current_labels.append(mock_label)

    mock_github.get_repo.return_value.get_pull.return_value.get_labels.return_value = (
        mock_current_labels
    )

    github.add_or_remove_labels(
        mock_github,
        "https://github.com/foo/bar/pull/10",
        add_label,
        remove_label,
        remove_namespaced,
    )

    mock_add_label.assert_called_once_with(
        mock_github.get_repo().get_pull(), expected_add
    )
    mock_remove_label.assert_called_once_with(mock_github.get_repo().get_pull(), ANY)
    # The order of the labels is not guaranteed, so we need to sort them
    sorted(mock_remove_label.call_args_list[0][0][1]) == sorted(expected_remove)


def test_add_labels_to_pull_request() -> None:
    mock_pull_request = MagicMock()
    github.add_labels_to_pull_request(mock_pull_request, ["label1", "label2"])

    mock_pull_request.add_to_labels.assert_has_calls([call("label1"), call("label2")])


def test_remove_labels_from_pull_request() -> None:
    mock_pull_request = MagicMock()
    github.remove_labels_from_pull_request(mock_pull_request, ["label1", "label2"])

    mock_pull_request.remove_from_labels.assert_has_calls(
        [call("label1"), call("label2")]
    )


def test_open_pull_request() -> None:
    mock_client = MagicMock()
    mock_repo = MagicMock()
    mock_pull_request = MagicMock()

    mock_client.get_repo.return_value = mock_repo
    mock_repo.create_pull.return_value = mock_pull_request

    resp = github.open_pull_request(
        mock_client, "repo_name", "title", "body", "branch", "base"
    )

    mock_client.get_repo.assert_called_once_with("repo_name")
    mock_repo.create_pull.assert_called_once_with(
        title="title", body="body", head="branch", base="base"
    )

    assert resp == mock_pull_request


def test_get_pull_request_by_number() -> None:
    mock_client = MagicMock()
    mock_repo = MagicMock()
    mock_pull_request = MagicMock()

    mock_client.get_repo.return_value = mock_repo
    mock_repo.get_pull.return_value = mock_pull_request

    resp = github.get_pull_request_by_number(mock_client, "repo_name", 1)

    mock_client.get_repo.assert_called_once_with("repo_name")
    mock_repo.get_pull.assert_called_once_with(1)

    assert resp == mock_pull_request


def test_close_pull_request() -> None:
    mock_pull_request = MagicMock()

    resp = github.close_pull_request(mock_pull_request)

    mock_pull_request.edit.assert_called_once_with(state="closed")

    assert resp == mock_pull_request


def test_copy_branch_creates_new_branch() -> None:
    mock_client = MagicMock()
    mock_src_repo = MagicMock()
    dest_repo = MagicMock()

    mock_client.get_repo.side_effect = [mock_src_repo, dest_repo]

    src_branch = MagicMock()
    src_branch.commit.sha = "123abc"
    mock_src_repo.get_branch.return_value = src_branch

    dest_repo.get_branches.return_value = []

    github.copy_branch(
        mock_client,
        "org/source-repo",
        "feature-branch",
        "org/destination-repo",
        "new-feature-branch",
    )

    dest_repo.create_git_ref.assert_called_once_with(
        ref="refs/heads/new-feature-branch", sha="123abc"
    )


def test_copy_branch_updates_existing_branch() -> None:
    mock_client = MagicMock()
    mock_src_repo = MagicMock()
    dest_repo = MagicMock()

    mock_client.get_repo.side_effect = [mock_src_repo, dest_repo]

    src_branch = MagicMock()
    src_branch.commit.sha = "123abc"
    mock_src_repo.get_branch.return_value = src_branch

    demo_branch = MagicMock()
    demo_branch.name = "demo"
    dest_branch = MagicMock()
    dest_branch.name = "dest_existing_branch"
    dest_repo.get_branches.return_value = [dest_branch, demo_branch]

    dest_branch_ref = MagicMock()
    dest_repo.get_git_ref.return_value = dest_branch_ref

    github.copy_branch(
        mock_client,
        "org/source-repo",
        "feature-branch",
        "org/destination-repo",
        "dest_existing_branch",
    )

    dest_repo.get_git_ref.assert_called_once_with("heads/dest_existing_branch")
    dest_branch_ref.edit.assert_called_once_with(sha="123abc", force=True)


def test_delete_branch_success() -> None:
    mock_client = MagicMock()
    mock_repo = MagicMock()
    mock_client.get_repo.return_value = mock_repo

    target_branch = MagicMock()
    target_branch.name = "old-feature-branch"
    mock_repo.get_branches.return_value = [target_branch]

    branch_ref = MagicMock()
    mock_repo.get_git_ref.return_value = branch_ref

    github.delete_branch(mock_client, "org/repo-name", "old-feature-branch")

    mock_repo.get_git_ref.assert_called_once_with("heads/old-feature-branch")
    branch_ref.delete.assert_called_once()


def test_delete_branch_when_branch_does_not_exist() -> None:
    mock_client = MagicMock()
    mock_repo = MagicMock()
    mock_client.get_repo.return_value = mock_repo

    mock_repo.get_branches.return_value = []

    github.delete_branch(mock_client, "org/repo-name", "non-existent-branch")

    mock_repo.get_git_ref.assert_not_called()
