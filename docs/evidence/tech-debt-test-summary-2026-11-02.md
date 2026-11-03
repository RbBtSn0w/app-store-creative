## ✅ CI tests passed

Cross-filesystem tests passed: 33 tests, 0 skipped; owned volume cleanup passed.

## ✅ Unit tests passed

**1,288 passed** · 34 skipped · 4/4 shards reported · 43m 41s wall time

### Shards

| Shard | Result | Tests | Skipped | Duration |
| --- | --- | ---: | ---: | ---: |
| 1/4 | ✅ Passed | 334 | 0 | 13m 12s |
| 2/4 | ✅ Passed | 420 | 1 | 7m 26s |
| 3/4 | ✅ Passed | 270 | 16 | 4m 02s |
| 4/4 | ✅ Passed | 298 | 17 | 10m 45s |

<details><summary>Slowest 10 tests</summary>

| Duration | Test | Shard |
| ---: | --- | ---: |
| 87.0s | `NativePreviewArchiveTests.test_sealed_recipe_replays_after_original_workspace_is_removed`<br><sub>test_native_preview_archive</sub> | 1 |
| 50.3s | `NativePreviewArchiveTests.test_registered_recording_recipe_replays_after_workspace_removal`<br><sub>test_native_preview_archive</sub> | 1 |
| 41.2s | `PurgeProcessCrashTests.test_receipt_process_death_resumes_public_purge`<br><sub>test_purge_process_crash</sub> | 4 |
| 31.4s | `RelocationQuarantinePreparationTests.test_preparation_copies_media_and_keeps_source`<br><sub>test_relocation_quarantine_preparation</sub> | 1 |
| 28.4s | `RelocationQuarantinePreparationTests.test_complete_payload_sync_interruption_can_resume`<br><sub>test_relocation_quarantine_preparation</sub> | 1 |
| 28.0s | `LocalReverseExecutionTests.test_real_git_public_reverse_cli_completes_three_round_trip_switches`<br><sub>test_configuration_local_reverse_execution</sub> | 3 |
| 27.9s | `RelocationQuarantineInventoryTests.test_unknown_file_is_reported_and_preserved`<br><sub>test_relocation_quarantine_inventory</sub> | 4 |
| 24.4s | `RelocationRollbackTests.test_user_configuration_edit_is_never_overwritten`<br><sub>test_relocation_rollback</sub> | 4 |
| 23.5s | `RelocationRollbackTests.test_rollback_releases_source_and_preserves_inactive_targets`<br><sub>test_relocation_rollback</sub> | 4 |
| 22.4s | `RemoteObservationTests.test_evidence_forward_receipt_sigkill_rollback`<br><sub>test_remote_observations</sub> | 2 |

</details>

<details><summary>Skipped tests by reason (34)</summary>

| Count | Reason |
| ---: | --- |
| 33 | Explicit independently mounted test volume required |
| 1 | Requires an explicitly authorized seeded native window |

</details>

