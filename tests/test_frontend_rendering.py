"""Frontend regressions: preserve values, show every record, and reload new data."""

import json

import pandas as pd
from streamlit.testing.v1 import AppTest

from tests.test_app_roles import admin_app, project, workspace  # shared temporary-data fixtures
from frontend.recognition_chart import recognition_chart, recognition_data, awareness_order
from frontend.tables import column_layout
from frontend.dashboard_charts import staff_chart, pressure_chart


def populate(workspace):
    phishing = next(e for e in workspace.emails if e["label"] == "phishing")
    safe = next(e for e in workspace.emails if e["label"] == "legitimate")
    for i, person in enumerate(workspace.people):
        workspace.twin.update(person.id, phishing, "click" if i % 2 else "report", source="app")
        workspace.twin.update(person.id, safe, "report" if i % 3 else "ignore", source="app")
    return phishing, safe


def score_table(app):
    return next(t.value for t in app.dataframe if "judged" in t.value.columns)


def test_dashboard_chart_sizes_and_score_values_are_preserved(workspace):
    populate(workspace)
    app = admin_app()
    assert not app.exception and not app.error
    charts = [json.loads(chart.proto.spec) for chart in app.get("vega_lite_chart")]
    assert charts[0]["height"]["step"] >= 30
    assert charts[0]["layer"][0]["encoding"]["x"]["field"] == "click_rate"
    assert charts[1]["layer"][0]["encoding"]["y"]["field"] == "rate"
    assert charts[0]["config"]["axis"]["labelFontSize"] >= 14
    table = score_table(app)
    assert len(table) == len(workspace.people)
    for person in workspace.people:
        row = table[table["name"] == person.name].iloc[0]
        expected = workspace.twin.get_score(person.id)
        assert row["judged"] == expected["answered"]
        assert row["correct"] == expected["correct"]
        assert row["accuracy"] == round(100 * expected["accuracy"])
    assert "Table view" not in [e.label for e in app.expander]


def test_new_records_refresh_the_single_score_table_and_keep_optional_details(workspace):
    phishing, safe = populate(workspace)
    app = admin_app()
    person = workspace.people[0]
    before = score_table(app).set_index("name").loc[person.name, "judged"]
    columns = app.multiselect(key="dashboard_columns")
    columns.set_value(columns.value + ["phishing seen", "click rate", "role"]).run()
    workspace.twin.update(person.id, safe, "ignore", source="app")
    app.run()
    table = score_table(app).set_index("name")
    assert table.loc[person.name, "judged"] == before + 1
    assert table.loc[person.name, "phishing seen"] == 1
    assert "click rate" in table.columns and "role" in table.columns
    assert len([t for t in app.dataframe if "judged" in t.value.columns]) == 1


def test_genuine_only_practice_reaches_existing_judgement_table(workspace):
    from backend import store
    from backend.email_builder import EmailBuilder
    from backend.training import submit_answer
    from tests.test_app_roles import authorized_service

    app = admin_app()
    assert any("No history yet" in item.value for item in app.info)
    builder = EmailBuilder(workspace.generator)
    pool = [builder.build_legitimate(base=workspace.generator.by_id[38], new_id=1000),
            builder.build_legitimate(base=workspace.generator.by_id[39], new_id=1001)]
    store.save_generated(pool, str(workspace.data / "generated_emails.json"))
    person = workspace.people[2]
    service = authorized_service(workspace.root)
    session = service.assign_practice(workspace, person.id, 2, "dashboard-genuine-request")
    for index, email in enumerate(session["emails"]):
        submit_answer(workspace, person.id, email["id"], bool(index))
    saved = (workspace.data / "history_log.jsonl").read_bytes()
    app.run()
    assert not app.exception and not app.error
    assert not any("No history yet" in item.value for item in app.info)
    row = score_table(app).iloc[0]
    assert row["name"] == person.name
    assert (row["judged"], row["correct"], row["incorrect"], row["accuracy"]) == (2, 1, 1, 50)
    assert len(app.dataframe) == 1 and not app.get("vega_lite_chart")
    # Refresh and a new browser session must read the saved answers, not add them again.
    app.run()
    fresh = admin_app()
    pd.testing.assert_frame_equal(score_table(app), score_table(fresh))
    assert (workspace.data / "history_log.jsonl").read_bytes() == saved
    assert len(json.loads((workspace.data / "responses.json").read_text())) == 2


def test_run_live_practice_and_cli_update_existing_dashboard_without_duplicate_results(workspace):
    import subprocess
    import sys
    import pytest
    from streamlit.dataframe_util import convert_arrow_bytes_to_pandas_df

    from backend import store
    from backend.training import submit_answer, Workspace
    from backend.metrics import workforce_frame
    from tests.test_app_roles import authorized_service, seed_training, ROOT

    seed_training(workspace)
    service = authorized_service(workspace.root)
    experiment_person, practice_person = workspace.people[:2]
    app = admin_app()
    assert service.run_many(workspace, 4, targets=[experiment_person],
                            build_new=False, allow_repeats=False) == (4, 0)
    app.run()
    assert score_table(app).iloc[0]["judged"] == 4
    before_practice = (workspace.data / "history_log.jsonl").read_bytes()
    session = service.assign_practice(workspace, practice_person.id, 4, "dashboard-mixed-request")
    assert (workspace.data / "history_log.jsonl").read_bytes() == before_practice
    for index, email in enumerate(session["emails"]):
        answer = email["label"] == "phishing"
        submit_answer(workspace, practice_person.id, email["id"], answer if index % 2 else not answer)
    app.run()
    assert sorted(score_table(app)["judged"].tolist()) == [4, 4]
    assert score_table(app).set_index("name").loc[practice_person.name, "accuracy"] == 50
    saved = (workspace.data / "history_log.jsonl").read_bytes()
    with pytest.raises(ValueError, match="already been answered"):
        submit_answer(workspace, practice_person.id, session["emails"][0]["id"], True)
    assert (workspace.data / "history_log.jsonl").read_bytes() == saved

    record = service.deliver_one(workspace, person=experiment_person, build_new=True)
    assert record is not None
    service.save_workspace(workspace, generated=True)
    for script, arguments in (("main.py", [experiment_person.id, "2", "--reader"]),
                              ("live.py", ["--rounds", "2", "--speed", "0", "--plain"])):
        result = subprocess.run([sys.executable, str(ROOT / script), *arguments],
                                cwd=workspace.root, capture_output=True, text=True, timeout=30)
        assert result.returncode == 0, result.stderr
    app.run()
    assert not app.exception and not app.error
    current = Workspace(workspace.root)
    try:
        events = [event for person in current.people for event in current.twin.get_history(person.id)]
        assert len(events) == 13
        assert sum(event["source"] == "app" for event in events) == 4
        assert sum(score_table(app)["judged"]) == len(events)
        assert (workspace.data / "history_log.jsonl").read_bytes().startswith(saved)
        wf = workforce_frame(current.twin, current.people)
        phishing = [event for event in events if event["label"] == "phishing"]
        metrics = {metric.label: metric.value for metric in app.metric}
        assert metrics["Phishing delivered"] == str(len(phishing))
        assert metrics["Clicked"] == "%.0f%%" % (100 * sum(e["action"] == "click" for e in phishing) / len(phishing))
        assert metrics["Recognised"] == "%.0f%%" % (100 * sum(e["action"] == "report" for e in phishing) / len(phishing))
        assert metrics["Staff tracked"] == str(int((wf["seen"] > 0).sum()))
        charts = list(app.get("vega_lite_chart"))
        assert len(charts) == 3
        chart_data = [convert_arrow_bytes_to_pandas_df(chart.proto.datasets[0].data.data)
                      for chart in charts]
        staff_rows = next(frame for frame in chart_data if "person_key" in frame)
        assert staff_rows["seen"].sum() == len(phishing)
        expected_comparison = recognition_data(wf)
        actual_comparison = next(frame for frame in chart_data if "response" in frame)
        pd.testing.assert_frame_equal(
            actual_comparison[expected_comparison.columns].reset_index(drop=True),
            expected_comparison.reset_index(drop=True), check_dtype=False)
        cue_rows = next(frame for frame in chart_data if "fooled" in frame)
        assert cue_rows["asked"].sum() == len(phishing)
        assert cue_rows["fooled"].sum() == sum(not e["correct"] for e in phishing)
        for person in current.people:
            score = current.twin.get_score(person.id)
            if score["answered"]:
                row = score_table(app).set_index("name").loc[person.name]
                assert row["judged"] == score["answered"]
                assert row["correct"] == score["correct"]
                assert row["accuracy"] == round(100 * score["accuracy"])
    finally:
        current.close()
    # Reloading reports never appends results, and all current table values survive a new session.
    saved = (workspace.data / "history_log.jsonl").read_bytes()
    app.run()
    pd.testing.assert_frame_equal(score_table(app), score_table(admin_app()))
    assert (workspace.data / "history_log.jsonl").read_bytes() == saved
    assert len(store.load_responses(str(workspace.data / "responses.json"))) == 4


def test_all_cues_have_room_and_comparison_has_horizontal_groups(workspace):
    # Exercise all five cues, including adjacent HR/payroll and IT login rows.
    phishing = {e["cue"]: e for e in workspace.emails if e["label"] == "phishing"}
    for person in workspace.people:
        for email in phishing.values():
            workspace.twin.update(person.id, email, "click", source="app")
    app = admin_app()
    charts = [json.loads(chart.proto.spec) for chart in app.get("vega_lite_chart")]
    comparison = charts[1]["layer"][0]["encoding"]
    assert comparison["x"]["field"] == "awareness"
    assert comparison["x"]["axis"]["labelAngle"] == 0
    assert comparison["x"]["sort"] == ["Low", "Medium", "High"]
    assert comparison["xOffset"]["field"] == "response"
    cue_chart = charts[2]
    assert cue_chart["height"]["step"] >= 30
    assert cue_chart["layer"][0]["encoding"]["y"]["axis"]["labelOverlap"] is False
    table = next(t.value for t in app.dataframe if "cue" in t.value.columns)
    assert {"IT login", "HR / payroll"} <= set(table["cue"])
    assert all(table["rate"] == 100)
    assert table["asked"].sum() == len(workspace.people) * len(phishing)


def test_staff_rows_keep_duplicate_and_long_names_and_zero_rates():
    frame = pd.DataFrame([
        {"id": "P1", "name": "Professor Alexandra Catherine Montgomery-Sutherland",
         "role": "Lead", "awareness": "expert", "seen": 2, "clicked": 2, "click_rate": 1.0},
        {"id": "P2", "name": "Professor Alexandra Catherine Montgomery-Sutherland",
         "role": "Lead", "awareness": "high", "seen": 2, "clicked": 0, "click_rate": 0.0}])
    before = frame.copy(deep=True)
    spec = staff_chart(frame).to_dict()
    assert spec["height"]["step"] >= 44  # Wrapped names get room for every line.
    assert spec["layer"][0]["encoding"]["y"]["sort"] == ["P1", "P2"]
    assert "expert" in spec["layer"][0]["encoding"]["color"]["scale"]["domain"]
    data = next(iter(spec["datasets"].values()))
    assert [row["click_rate"] for row in data] == [1, 0]
    pd.testing.assert_frame_equal(frame, before)
    larger = pd.concat([frame.assign(id=lambda f: f.id + str(i)) for i in range(100)])
    assert staff_chart(larger).to_dict()["height"] == spec["height"]


def test_pressure_progress_tracks_preserve_rates_and_row_order():
    frame = pd.DataFrame({"display_type": ["A long pressure category for a test", "IT login"],
                          "asked": [4, 10], "fooled": [0, 10], "rate": [0.0, 1.0]})
    before = frame.copy(deep=True)
    spec = pressure_chart(frame).to_dict()
    assert len(spec["layer"]) == 3  # Track, measured value and percentage.
    assert spec["layer"][1]["encoding"]["x"]["field"] == "rate"
    assert spec["layer"][1]["encoding"]["x"]["axis"] is None
    assert spec["layer"][2]["encoding"]["text"]["format"] == ".0%"
    assert spec["height"]["step"] >= 30
    pd.testing.assert_frame_equal(frame, before)


def test_email_catalogue_does_not_drop_older_records_and_accepts_new_ones(workspace):
    for i in range(520):
        email = dict(workspace.emails[0], id=1000 + i, subject="Fixture email %d" % i)
        workspace.generated.append(email)
    workspace.save(generated=True)
    app = admin_app("Emails")
    listing = next(t.value for t in app.dataframe if "sender" in t.value.columns)
    assert len(listing) == 520 and "1000" in listing["id"].tolist()
    assert len(app.selectbox(key="open_email").options) == 520
    workspace.generated.append(dict(workspace.emails[0], id=2000, subject="New record"))
    workspace.save(generated=True)
    app.run()
    listing = next(t.value for t in app.dataframe if "sender" in t.value.columns)
    assert len(listing) == 521 and "2000" in listing["id"].tolist()


def test_short_large_and_empty_tables_use_the_same_component():
    app = AppTest.from_string('''
import pandas as pd
from frontend.tables import show_table
show_table(pd.DataFrame({"record": range(2)}))
show_table(pd.DataFrame({"record": range(2000)}))
show_table(pd.DataFrame())
''').run()
    assert not app.exception
    assert [len(t.value) for t in app.dataframe] == [2, 2000]
    assert all(t.proto.row_height == 34 for t in app.dataframe)
    assert any("No records" in info.value for info in app.info)


def test_table_columns_follow_content_and_keep_explicit_configuration():
    frame = pd.DataFrame({"name": ["Dr. Marcus Ellery"], "judged": [120],
                          "accuracy": [90], "description": ["Long teaching note " * 10]})
    config = {"accuracy": {"label": "Accuracy", "type_config": {"type": "progress"}},
              "judged": {"label": "Judged"}}
    untouched = json.loads(json.dumps(config))
    sizing = column_layout(frame, config)
    assert sizing["judged"]["width"] < sizing["name"]["width"]
    assert sizing["accuracy"]["width"] < sizing["name"]["width"]
    assert sizing["description"]["width"] > sizing["name"]["width"]
    assert config == untouched
    frame["new_field"] = ["New data column"]
    assert "new_field" in column_layout(frame, config)


def test_table_widths_notice_long_values_in_the_middle_of_large_data():
    frame = pd.DataFrame({"name": ["Sam"] * 200})
    before = column_layout(frame)["name"]["width"]
    frame.loc[100, "name"] = "Professor Alexandra Montgomery"
    assert column_layout(frame)["name"]["width"] > before


def test_history_keeps_summary_and_export_in_a_compact_view(workspace):
    populate(workspace)
    app = admin_app("All history")
    assert not app.exception and not app.error
    assert "Per-person results" in [e.label for e in app.expander]
    summary = next(t.value for t in app.dataframe if "Q" in t.value.columns)
    assert len(summary) == len(workspace.people)
    history = next(t.value for t in app.dataframe if "probability" in t.value.columns)
    assert len(history) == 2 * len(workspace.people)
    assert len(app.get("download_button")) == 1


def test_recognition_uses_delivery_weighted_denominators_including_ignored():
    original = pd.DataFrame([
        {"awareness": "low", "seen": 10, "clicked": 1, "reported": 2},
        {"awareness": "low", "seen": 90, "clicked": 89, "reported": 0},
        {"awareness": "high", "seen": 10, "clicked": 2, "reported": 3},
        {"awareness": "medium", "seen": 0, "clicked": 0, "reported": 0},
    ])
    untouched = original.copy(deep=True)
    data = recognition_data(original).set_index(["awareness", "response"])
    assert data.loc[("Low", "Clicked"), "rate"] == 0.9
    assert data.loc[("Low", "Recognised"), "rate"] == 0.02
    assert data.loc[("High", "Clicked"), "rate"] == 0.2
    assert data.loc[("High", "Recognised"), "rate"] == 0.3
    assert set(data.index.get_level_values("awareness")) == {"Low", "High"}
    pd.testing.assert_frame_equal(original, untouched)


def test_recognition_handles_new_levels_missing_values_zero_and_empty_data():
    assert recognition_data(pd.DataFrame()).empty
    assert recognition_data(pd.DataFrame([{"awareness": "low", "seen": 0}])).empty
    data = recognition_data(pd.DataFrame([
        {"awareness": "expert", "seen": 4, "clicked": 4, "reported": 0},
        {"awareness": "high", "seen": 4, "clicked": 0, "reported": 4},
        {"awareness": None, "seen": 2, "clicked": None, "reported": None},
    ]))
    assert awareness_order(data) == ["High", "Expert", "Unknown"]
    assert data[data["awareness"] == "Unknown"]["rate"].eq(0).all()
    spec = recognition_chart(data).to_dict()
    enc = spec["layer"][0]["encoding"]
    assert enc["x"]["sort"] == ["High", "Expert", "Unknown"]
    assert enc["y"]["scale"]["domain"] == [0, 1]
    assert enc["xOffset"]["sort"] == ["Clicked", "Recognised"]
    assert spec["layer"][1]["encoding"]["text"]["format"] == ".0%"
    assert enc["tooltip"][2]["format"] == ".2%"
