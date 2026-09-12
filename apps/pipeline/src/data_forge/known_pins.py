"""既知の逸脱値レジストリ: 機械検証が原資料の真実として受容する、あるべき基準からの逸脱値の一元管理。

検算エンジン（`area.reconcile` / `sanity`）は値を持たず引数で受ける（機構と政策の分離）。
本モジュールは「受容する逸脱の値」だけを一箇所へ集め、**値を明記して固定＝ずれたら失敗**
（大きさの回帰も捕捉）させる。3 系統:
    - KNOWN_DIFFS / KNOWN_DIFF_REASONS … 人口保存（national_conservation）の既知差分。
    - CROSSFACT_C4 / CROSSFACT_C5 … クロスファクト検算の遡及年 Σ|diff| 値（`area/specs.py` の該当 spec が参照）。
    - KNOWN_NEGATIVES … 値サニティ（sanity.unknown_negatives）が受容する負値セル。

値の意味・許容理由（why）は docs/data-quality-assurance.md「既知の逸脱値レジストリ」が正典。
スペック定義（`CrossFactSpec` / `CROSSFACT`）は `area/specs.py`、値サニティの型・機構は `sanity.py` に残す
（＝定義・機構は各モジュール、値だけ本モジュールへ集約する）。
"""

from data_forge.sanity import KnownNegative

# ① 人口保存の既知差分（原資料特性で受容する年 → 期待差分）。national_conservation へ引数で渡す。
# 孤児やロジック不整合とは別物で、override では解消しない「原資料の真実」。
KNOWN_DIFFS: dict[int, int] = {1980: 37}
KNOWN_DIFF_REASONS: dict[int, str] = {
    1980: "東京都特別区部の区未定分（23区に按分されない集計差）",
}

# ② クロスファクト検算の遡及年 Σ|diff| 値 pin（`area/specs.py` の C4/C5 spec が known_pins へ参照）。
# 近年（2010〜2020）は厳密 diff=0 で、遡及年のみ別プロダクト間の集計差が残る。
CROSSFACT_C4: dict[int, int] = {1980: 8666, 1985: 8600, 1990: 8648, 1995: 8508, 2000: 8160, 2005: 28574}
CROSSFACT_C5: dict[int, int] = {1990: 326357, 1995: 130973, 2000: 228561, 2005: 482341}

# ③ 値サニティが受容する既知負値（型・機構は sanity.py）。table_name（＝family）→ 受容する負値セル。
# 原資料が保存則を満たさず不詳導出（総数−Σ内訳）が負に沈むセルを、原資料確認のうえ値付きで固定受容する。
KNOWN_NEGATIVES: dict[str, list[KnownNegative]] = {
    "labor_force": [
        KnownNegative(
            match={"area_code": "47000", "year": 1955, "sex_code": "1", "labor_status_code": "999"},
            measure="population",
            value=-100,
            reason="沖縄1955男: 本土復帰前・抽出集計の百人丸めで原資料のΣ内訳(労+非)が総数を100超過",
        ),
        KnownNegative(
            match={"area_code": "47000", "year": 1985, "sex_code": "2", "labor_status_code": "999"},
            measure="population",
            value=-9289,
            reason="沖縄1985女: e-Stat時系列製品の公表値が内部不整合(労+非=449,374 > 総数440,085)＝原資料由来",
        ),
    ],
}
