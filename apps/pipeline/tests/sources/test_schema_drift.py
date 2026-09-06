"""新年度スキーマ・ドリフト検出（schema_drift.py）の単体テスト（ネットワーク不要）。

入口ガードが passthrough で素通しする軸構成の変化を、コミット済みスナップショットとの
差分で捕える計器を固める。「未カバー領域: 新年度スキーマ」の消化。
- axis_signature: 分類軸（tab/cat0N）はコードを pin・area/time は存在のみ（コード無し）
- diff_signature: 軸の増減／軸名変更／分類コードの増減を検出・area/time のコード差は無視
- load_registry / save_registry: 未作成なら空・書いた内容を読み戻せる

設計の正典は schema_drift.py の docstring、ゲートは docs/data-quality-assurance.md。
"""

from data_forge.sources.estat import schema_drift


def _raw(class_objs: list[dict]) -> dict:
    return {"GET_STATS_DATA": {"STATISTICAL_DATA": {"CLASS_INF": {"CLASS_OBJ": class_objs}}}}


def _sig_raw() -> dict:
    return _raw(
        [
            {"@id": "tab", "@name": "人口", "CLASS": {"@code": "020", "@name": "人口"}},
            {
                "@id": "cat01",
                "@name": "男女",
                "CLASS": [
                    {"@code": "100", "@name": "総数"},
                    {"@code": "110", "@name": "男"},
                    {"@code": "120", "@name": "女"},
                ],
            },
            {"@id": "area", "@name": "全国・都道府県", "CLASS": {"@code": "00000", "@name": "全国"}},
            {"@id": "time", "@name": "時間軸", "CLASS": {"@code": "2020000000", "@name": "2020年"}},
        ]
    )


# --- axis_signature ---


def test_axis_signature_pins_class_axes_and_unpins_area_time():
    sig = schema_drift.axis_signature(_sig_raw())

    assert set(sig) == {"tab", "cat01", "area", "time"}
    assert sig["cat01"] == {"name": "男女", "codes": ["100", "110", "120"]}
    assert sig["tab"] == {"name": "人口", "codes": ["020"]}  # 単一 dict CLASS もリスト化
    assert "codes" not in sig["area"]  # 年で変動＝pin しない
    assert "codes" not in sig["time"]
    assert sig["area"]["name"] == "全国・都道府県"


# --- diff_signature ---


def test_diff_signature_no_drift_on_identical():
    sig = schema_drift.axis_signature(_sig_raw())
    diff = schema_drift.diff_signature(sig, sig)
    assert not diff.has_drift


def test_diff_signature_detects_axis_add_and_remove():
    expected = schema_drift.axis_signature(_sig_raw())
    actual = schema_drift.axis_signature(
        _raw(
            [
                {"@id": "tab", "@name": "人口", "CLASS": {"@code": "020", "@name": "人口"}},
                {"@id": "cat02", "@name": "年齢", "CLASS": {"@code": "001", "@name": "総数"}},
                {"@id": "area", "@name": "全国・都道府県", "CLASS": {"@code": "00000", "@name": "全国"}},
                {"@id": "time", "@name": "時間軸", "CLASS": {"@code": "2025000000", "@name": "2025年"}},
            ]
        )
    )
    diff = schema_drift.diff_signature(expected, actual)

    assert diff.has_drift
    assert diff.axes_added == ["cat02"]
    assert diff.axes_removed == ["cat01"]


def test_diff_signature_detects_code_and_name_changes_on_class_axis():
    expected = schema_drift.axis_signature(_sig_raw())
    actual = schema_drift.axis_signature(
        _raw(
            [
                {"@id": "tab", "@name": "人口", "CLASS": {"@code": "020", "@name": "人口"}},
                {
                    "@id": "cat01",
                    "@name": "男女別",  # 名称変更
                    "CLASS": [
                        {"@code": "100", "@name": "総数"},
                        {"@code": "110", "@name": "男"},
                        {"@code": "130", "@name": "不詳"},  # 120 削除・130 追加
                    ],
                },
                {"@id": "area", "@name": "全国・都道府県", "CLASS": {"@code": "00000", "@name": "全国"}},
                {"@id": "time", "@name": "時間軸", "CLASS": {"@code": "2020000000", "@name": "2020年"}},
            ]
        )
    )
    diff = schema_drift.diff_signature(expected, actual)

    assert diff.name_changed == {"cat01": ("男女", "男女別")}
    assert diff.codes_added == {"cat01": ["130"]}
    assert diff.codes_removed == {"cat01": ["120"]}


def test_diff_signature_ignores_area_time_code_variation():
    # area/time はコードを pin しないため、コードが年で変わっても差分にならない。
    expected = schema_drift.axis_signature(_sig_raw())
    actual = schema_drift.axis_signature(
        _raw(
            [
                {"@id": "tab", "@name": "人口", "CLASS": {"@code": "020", "@name": "人口"}},
                {
                    "@id": "cat01",
                    "@name": "男女",
                    "CLASS": [
                        {"@code": "100", "@name": "総数"},
                        {"@code": "110", "@name": "男"},
                        {"@code": "120", "@name": "女"},
                    ],
                },
                {"@id": "area", "@name": "全国・都道府県", "CLASS": {"@code": "13000", "@name": "東京都"}},
                {"@id": "time", "@name": "時間軸", "CLASS": {"@code": "2025000000", "@name": "2025年"}},
            ]
        )
    )
    assert not schema_drift.diff_signature(expected, actual).has_drift


# --- registry IO ---


def test_registry_roundtrip(tmp_path):
    path = tmp_path / "snap.json"
    assert schema_drift.load_registry(path) == {}  # 未作成は空

    sig = schema_drift.axis_signature(_sig_raw())
    schema_drift.save_registry({"0003448237": sig}, path)

    assert schema_drift.load_registry(path) == {"0003448237": sig}
