"""既知の逸脱値レジストリ: 機械検証が原資料の真実として受容する、あるべき基準からの逸脱値の一元管理。

検算エンジン（`area.reconcile` / `sanity`）は値を持たず引数で受ける（機構と政策の分離）。
本モジュールは「受容する逸脱の値」だけを一箇所へ集め、
**値を明記して固定＝ずれたら失敗**（大きさの回帰も捕捉）させる。
3 系統:
    - CONSERVATION_DIFFS（KnownDiff）… 人口保存（national_conservation）の既知差分。
    - CROSSFACT_C4 / CROSSFACT_C5 … クロスファクト検算の遡及年 Σ|diff| 値（`area/specs.py` の該当 spec が参照）。
    - SANITY_NEGATIVES … 値サニティ（sanity.unknown_negatives）が受容する負値セル。

値の意味・許容理由（why）は docs/data-quality-assurance.md「既知の逸脱値レジストリ」が正典。

**分担の原則: 型・機構は各実装、具体値だけ本モジュール**。
レコード型 `KnownDiff`（年グレイン）は `area/reconcile.py`、`KnownNegative`（セルグレイン）は `sanity.py`、
スペック定義 `CrossFactSpec` / `CROSSFACT` は `area/specs.py`（＝それぞれのエンジン／政策側）に置き、
本モジュールは凍結した具体値のインスタンスだけを集約して1ファイルで監査可能にする。
"""

from data_forge.area.reconcile import KnownDiff
from data_forge.sanity import KnownNegative

# ① 人口保存の既知差分（原資料特性で受容する年 → 期待差分）。
# reconcile.year_pins で dict 化し national_conservation へ渡す。
# 孤児やロジック不整合とは別物で、override では解消しない「原資料の真実」。
CONSERVATION_DIFFS: list[KnownDiff] = [
    KnownDiff(1980, 37, "東京都特別区部の区未定分（23区に按分されない集計差）"),
]

# ② クロスファクト検算の遡及年 Σ|diff| 値 pin（`area/specs.py` の C4/C5 spec が known_pins へ参照）。
# 近年（2010〜2020）は厳密 diff=0 で、遡及年のみ別プロダクト間の集計差が残る。
CROSSFACT_C4: dict[int, int] = {1980: 8666, 1985: 8600, 1990: 8648, 1995: 8508, 2000: 8160, 2005: 28574}
# C5 の pin = 確定人口(人口等基本集計) − 夜間人口(従業地・通学地集計 常住地総数)。
# 差は別系統の集計に由来し 2010 の全数集計化で消滅（=集計系統/母集団定義差）。
# 差の理由は docs/data-quality-assurance.md「既知の逸脱値レジストリ ②」が正典。
CROSSFACT_C5: dict[int, int] = {1990: 326357, 1995: 130973, 2000: 228561, 2005: 482341}
# H1 の pin = households ミクロ(回次別・2020境界へ合併畳込)→県rollup と マクロ(回次跨・各年境界) の Σ|diff|。
# 差は県跨ぎ合併の境界振替のみ（山口村: 長野→岐阜 中津川市 2005 等）＝両符号で県内±相殺し net=0。
# 2005 以降は境界一致で diff=0。世帯人員(H2)は県跨ぎ合併年(2005)より後の 2015/2020 のみ収録ゆえ pin 不要。
CROSSFACT_H1: dict[int, int] = {1985: 2324, 1990: 2368, 1995: 2420, 2000: 2488}

# ③ 値サニティが受容する既知負値（型・機構は sanity.py）。
# table_name（＝family）→ 受容する負値セル。
# 原資料が保存則を満たさず不詳導出（総数−Σ内訳）が負に沈むセルを、原資料確認のうえ値付きで固定受容する。
SANITY_NEGATIVES: dict[str, list[KnownNegative]] = {
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
