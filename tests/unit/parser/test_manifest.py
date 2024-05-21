from argparse import Namespace
from unittest.mock import MagicMock, patch

import pytest
from pytest_mock import MockerFixture

from dbt.config import RuntimeConfig
from dbt.contracts.graph.manifest import Manifest
from dbt.flags import set_from_args
from dbt.parser.manifest import ManifestLoader
from dbt.parser.read_files import FileDiff
from dbt.tracking import User


class TestPartialParse:
    @patch("dbt.parser.manifest.ManifestLoader.build_manifest_state_check")
    @patch("dbt.parser.manifest.os.path.exists")
    @patch("dbt.parser.manifest.open")
    def test_partial_parse_file_path(self, patched_open, patched_os_exist, patched_state_check):
        mock_project = MagicMock(RuntimeConfig)
        mock_project.project_target_path = "mock_target_path"
        patched_os_exist.return_value = True
        ManifestLoader(mock_project, {})
        # by default we use the project_target_path
        patched_open.assert_called_with("mock_target_path/partial_parse.msgpack", "rb")
        set_from_args(Namespace(partial_parse_file_path="specified_partial_parse_path"), {})
        ManifestLoader(mock_project, {})
        # if specified in flags, we use the specified path
        patched_open.assert_called_with("specified_partial_parse_path", "rb")

    def test_profile_hash_change(self, mock_project):
        # This test validate that the profile_hash is updated when the connection keys change
        profile_hash = "750bc99c1d64ca518536ead26b28465a224be5ffc918bf2a490102faa5a1bcf5"
        mock_project.credentials.connection_info.return_value = "test"
        manifest = ManifestLoader(mock_project, {})
        assert manifest.manifest.state_check.profile_hash.checksum == profile_hash
        mock_project.credentials.connection_info.return_value = "test1"
        manifest = ManifestLoader(mock_project, {})
        assert manifest.manifest.state_check.profile_hash.checksum != profile_hash


class TestFailedPartialParse:
    @patch("dbt.tracking.track_partial_parser")
    @patch("dbt.tracking.active_user")
    @patch("dbt.parser.manifest.PartialParsing")
    @patch("dbt.parser.manifest.ManifestLoader.read_manifest_for_partial_parse")
    @patch("dbt.parser.manifest.ManifestLoader.build_manifest_state_check")
    def test_partial_parse_safe_update_project_parser_files_partially(
        self,
        patched_state_check,
        patched_read_manifest_for_partial_parse,
        patched_partial_parsing,
        patched_active_user,
        patched_track_partial_parser,
    ):
        mock_instance = MagicMock()
        mock_instance.skip_parsing.return_value = False
        mock_instance.get_parsing_files.side_effect = KeyError("Whoopsie!")
        patched_partial_parsing.return_value = mock_instance

        mock_project = MagicMock(RuntimeConfig)
        mock_project.project_target_path = "mock_target_path"

        mock_saved_manifest = MagicMock(Manifest)
        mock_saved_manifest.files = {}
        patched_read_manifest_for_partial_parse.return_value = mock_saved_manifest

        loader = ManifestLoader(mock_project, {})
        loader.safe_update_project_parser_files_partially({})

        patched_track_partial_parser.assert_called_once()
        exc_info = patched_track_partial_parser.call_args[0][0]
        assert "traceback" in exc_info
        assert "exception" in exc_info
        assert "code" in exc_info
        assert "location" in exc_info
        assert "full_reparse_reason" in exc_info
        assert "KeyError: 'Whoopsie!'" == exc_info["exception"]
        assert isinstance(exc_info["code"], str) or isinstance(exc_info["code"], type(None))


class TestGetFullManifest:
    @pytest.fixture
    def set_required_mocks(
        self, mocker: MockerFixture, manifest: Manifest, mock_adapter: MagicMock
    ):
        mocker.patch("dbt.parser.manifest.get_adapter").return_value = mock_adapter
        mocker.patch("dbt.parser.manifest.ManifestLoader.load").return_value = manifest
        mocker.patch("dbt.parser.manifest._check_manifest").return_value = None
        mocker.patch(
            "dbt.parser.manifest.ManifestLoader.save_macros_to_adapter"
        ).return_value = None
        mocker.patch("dbt.tracking.active_user").return_value = User(None)

    def test_write_perf_info(
        self,
        mock_project: MagicMock,
        mocker: MockerFixture,
        set_required_mocks,
    ) -> None:
        write_perf_info = mocker.patch("dbt.parser.manifest.ManifestLoader.write_perf_info")

        ManifestLoader.get_full_manifest(
            config=mock_project,
            # write_perf_info=False let it default instead
        )
        assert not write_perf_info.called

        ManifestLoader.get_full_manifest(config=mock_project, write_perf_info=False)
        assert not write_perf_info.called

        ManifestLoader.get_full_manifest(config=mock_project, write_perf_info=True)
        assert write_perf_info.called

    def test_reset(
        self,
        mock_project: MagicMock,
        mock_adapter: MagicMock,
        set_required_mocks,
    ) -> None:

        ManifestLoader.get_full_manifest(
            config=mock_project,
            # reset=False let it default instead
        )
        assert not mock_project.clear_dependencies.called
        assert not mock_adapter.clear_macro_resolver.called

        ManifestLoader.get_full_manifest(config=mock_project, reset=False)
        assert not mock_project.clear_dependencies.called
        assert not mock_adapter.clear_macro_resolver.called

        ManifestLoader.get_full_manifest(config=mock_project, reset=True)
        assert mock_project.clear_dependencies.called
        assert mock_adapter.clear_macro_resolver.called

    def test_partial_parse_file_diff_flag(
        self,
        mock_project: MagicMock,
        mocker: MockerFixture,
        set_required_mocks,
    ) -> None:

        # FileDiff.from_dict is only called if PARTIAL_PARSE_FILE_DIFF == False
        # So we can track this function call to check if setting PARTIAL_PARSE_FILE_DIFF
        # works appropriately
        mock_file_diff = mocker.patch("dbt.parser.read_files.FileDiff.from_dict")
        mock_file_diff.return_value = FileDiff([], [], [])

        ManifestLoader.get_full_manifest(config=mock_project)
        assert not mock_file_diff.called

        set_from_args(Namespace(PARTIAL_PARSE_FILE_DIFF=True), {})
        ManifestLoader.get_full_manifest(config=mock_project)
        assert not mock_file_diff.called

        set_from_args(Namespace(PARTIAL_PARSE_FILE_DIFF=False), {})
        ManifestLoader.get_full_manifest(config=mock_project)
        assert mock_file_diff.called
