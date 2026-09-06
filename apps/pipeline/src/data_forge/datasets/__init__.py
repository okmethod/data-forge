"""データセット定義レジストリ（universe 別サブパッケージのバレル）。

新しいデータセットの追加は、該当 universe/<family>.py にエントリを1つ足すだけで済むようにする。
ソース固有の取得・整形処理は sources/ 以下の関数を参照する。

正典の所在（ここには再掲しない＝ドリフト防止）:
- 命名規約（family / key / stem / table_name の関係・suffix の軸・未統一論点）
  … apps/pipeline/README.md「命名規則」
- 軸構造（tab/cat コード・年ごとのスキーマ差・全国行の有無・不詳の導出等）
  cleaner モジュール sources/estat/<name>.py の docstring
- statsDataId・e-Stat 原題・年カバレッジ … docs/distributions/<name>.md
- 派生（縫合／射影）フローの汎用意味論 … _types.py の StitchedDataset / ProjectedDataset の docstring

family は universe（母集団）ごとにサブパッケージへ分け、各 family の SUBREGISTRIES を本バレルが束ねる。
各 family.py の module docstring は次の構造に統一する（他所と重複させない）:
1. 要約行 … 「<和名> <family> family[（複数系列同居ならその注記）]。」
2. 「正典:」ブロック … 正典の所在を箇条書き（無理に1行に詰めない）:
   - 軸構造 … <cleaner>.py
   - statsDataId・カバレッジ … docs/distributions/<name>.md
3. 「固有判断:」ブロック … その family 固有の判断を箇条書き（1項目1論点）。
   観点例: cleaner/join/grain の選択・合併/射影の要否・地理分離方式。
インラインコメント（# …）はサブ辞書内の個別エントリ固有の注記に限る。

family 名の閉じた語彙は下記 FAMILIES に集約し、test で全 table_name ∈ FAMILIES を強制する。
"""

from data_forge.datasets import employed, households, population
from data_forge.datasets._types import (
    Dataset,
    DatasetEntry,
    ProjectedDataset,
    StitchedDataset,
)

# ファミリー台帳＝table_name の閉じた語彙（＝出力される論理 fact の一覧）。
# 各エントリの table_name は必ずこの集合の要素（test_datasets で強制）。
# 新 family 追加時のみここに1語足す。命名規約はモジュール docstring を参照。
FAMILIES: frozenset[str] = frozenset(
    {
        "population",  # 男女別人口
        "age3class",  # 年齢3区分×男女別人口
        "age5year",  # 年齢5歳階級×男女別人口（市区町村=ミクロ／県世紀=マクロ 同居）
        "daynight",  # 昼夜間人口
        "households",  # 世帯の種類別 世帯数・世帯人員
        "family_type",  # 家族類型16区分別 世帯数・世帯人員
        "labor_force",  # 労働力状態3区分×男女別人口
        "industry",  # 産業大分類×男女別就業者数
        "occupation_major12",  # 職業大分類（12区分）×就業者数
        "occupation_major10",  # 職業大分類（旧10区分）×就業者数
    }
)


# universe サブパッケージを docs 順（population→households→employed）に束ねる。
# キー重複は許さない（同名 key があれば追加時に気付けるよう検査）。
_SUBREGISTRIES = (
    *population.SUBREGISTRIES,
    *households.SUBREGISTRIES,
    *employed.SUBREGISTRIES,
)
DATASETS: dict[str, DatasetEntry] = {}
for _sub in _SUBREGISTRIES:
    DATASETS.update(_sub)
if len(DATASETS) != sum(len(_s) for _s in _SUBREGISTRIES):
    raise ValueError("DATASETS: サブ辞書間で key が重複しています")


def get_dataset(key: str) -> DatasetEntry:
    try:
        return DATASETS[key]
    except KeyError:
        available = ", ".join(sorted(DATASETS))
        raise KeyError(f"未知のデータセット: {key!r}（利用可能: {available}）") from None


__all__ = [
    "DATASETS",
    "FAMILIES",
    "Dataset",
    "DatasetEntry",
    "ProjectedDataset",
    "StitchedDataset",
    "get_dataset",
]
