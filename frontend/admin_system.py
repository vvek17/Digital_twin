"""Compact system cards with existing authorization and maintenance operations."""

import streamlit as st
from frontend.runtime import invalidate_workspace
from frontend.tables import show_table
from frontend.layout import card, columns


@st.fragment(run_every="15s")
def render_system(service):
    service.require_admin()
    active_job = bool(st.session_state.get("live_running") or st.session_state.get("run_running"))
    st.warning("Stop simulations and training in other windows or terminals before backup, "
               "restore, or cache clearing. Admin locks cannot detect those other writers.")
    if active_job:
        st.error("A Live or Run job is active in this session. Admin writes and cache clearing "
                 "are blocked until the job stops.")
    notice = st.session_state.pop("admin_notice", None)
    if notice:
        st.success(notice)
    files, health = columns(key="system_health")
    with files:
        _files(service, active_job)
    with health:
        _database(service, active_job)
        _integrity(service, active_job)
    backups, caches = columns(key="system_maintenance")
    with backups:
        _backups(service, active_job)
    with caches:
        _caches(service, active_job)


def _files(service, active_job):
    with card("Data files", key="card_system_files"):
        try:
            st.caption("JSONL counts are nonblank lines, including malformed ones. JSON counts are "
                       "top-level collection entries; snapshot entries are person keys. SQLite "
                       "counts sum the five tables. Times are UTC. Missing runtime files can be normal.")
            status = service.file_status()
            visible = ["file", "exists", "bytes", "records"]
            if any(row["error"] for row in status):
                visible.append("error")
            show_table(status, visible=visible)
            st.caption("Timestamps and other fields are available in the table's columns menu.")
        except Exception as exc:
            st.error("File status failed: %s" % exc)



def _database(service, active_job):
    with card("SQLite tables and views", key="card_system_database"):
        try:
            st.caption("Read-only queries. The database is not rebuilt or refreshed by this page.")
            show_table(service.database_status())
        except Exception as exc:
            st.error("Database status failed: %s" % exc)



def _integrity(service, active_job):
    with card("Integrity checks", key="card_system_integrity"):
        try:
            report = service.integrity()
            st.write("%d history lines · %d JSON objects · %d issues" % (
                report["records_read"], report["json_objects"], len(report["issues"])))
            st.caption("Checks curated and Live/Run generated email IDs, roster IDs, required "
                       "fields, duplicate IDs (including the on-demand CSV), and malformed history "
                       "lines. This does not repair data.")
            if report["issues"]:
                st.warning("Integrity issues found. Review these before restoring or running experiments.")
                st.json(report["counts"])
                show_table(report["issues"])
            else:
                st.success("No integrity issues found.")
        except Exception as exc:
            st.error("Integrity checks failed: %s" % exc)



def _backups(service, active_job):
    with card("Backups and restore", key="card_system_backups"):
        try:
            st.caption("Backups include the listed data files, a checksum manifest, and a copy of "
                       "the audit trail. They are saved under backups/. Secrets are excluded.")
            if st.button("Create backup", disabled=active_job):
                result = service.create_backup(active_job=active_job)
                st.session_state.admin_notice = "Created %s (%d files)." % (result["name"], result["files"])
                st.rerun()
            backups = service.list_backups()
            if backups:
                show_table(backups)
                selected = st.selectbox("Backup to restore", [b["name"] for b in backups])
                st.warning("Restore replaces the managed data files with the selected backup, "
                           "including saved history. Files absent from that backup are removed. "
                           "The current audit log is preserved. A new backup is made first.")
                with st.form("admin_restore"):
                    confirmation = st.text_input("Type RESTORE to confirm", key="admin_restore_confirmation")
                    restore = st.form_submit_button("Restore selected backup", disabled=active_job)
                if restore:
                    result = service.restore_backup(selected, confirmation, active_job=active_job)
                    service.clear_caches(st.cache_data.clear, st.cache_resource.clear, active_job=active_job)
                    invalidate_workspace()
                    st.session_state.admin_notice = (
                        "Restored %s. Previous state saved as %s. Return to the main app to "
                        "load restored data; reload any other open sessions." % (
                            result["restored"], result["pre_restore_backup"]))
                    st.rerun()
            else:
                st.info("No ALERT ZIP backups yet.")
        except Exception as exc:
            st.error("Backup/restore failed: %s" % exc)



def _caches(service, active_job):
    with card("Streamlit caches", key="card_system_caches"):
        try:
            st.caption("Clear cached data and resources together. Existing session counters remain; "
                       "use Reload saved history in the Admin sidebar to refresh them.")
            if st.button("Clear data and resource caches", disabled=active_job):
                service.clear_caches(st.cache_data.clear, st.cache_resource.clear, active_job=active_job)
                st.success("Data and resource caches cleared.")
        except Exception as exc:
            st.error("Cache clearing failed: %s" % exc)
