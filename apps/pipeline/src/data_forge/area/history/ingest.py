"""廃置分合（市区町村コード改正履歴）の生CSV → 正規化イベント。

出所: e-Stat「廃置分合等情報」（総務省 全国地方公共団体コードの改正履歴。1970〜、CSV DL 可）。
code 体系が人口データ（e-Stat）と一致するのが採用理由。
取得は当面ブラウザ検索フォーム経由の手動DL（自動フェッチは後追い）。
生CSVは data/raw/history/（.gitignore・再取得可）。

生CSVの実構造（e-Stat 2026-08 実物で確定）:
    列 = 標準地域コード / 都道府県 / 政令市･郡等 / (ふりがな) / 市区町村 / (ふりがな) /
         廃置分合等施行年月日(YYYY-MM-DD) / 改正事由
    ★「改正前/改正後コード」の列は無い。改正事由が**自由文でコードを括弧内に埋め込む**:
      編入   : 「石下町(08523)が水海道市(08211)に編入」          → 08523 → 08211
      新設合併: 「A町(x)、B町(y)…が合併し、C市(z)を新設」        → x,y… → z
      政令市 : 「堺市(27201)の堺市(27140)への政令指定都市施行」   → 27201 → 27140
      名称/市制: 「A(a)が…C市(c)に市制施行/名称変更」            → a → c
    かつ**消滅した旧コードも標準地域コード行として存在**するため、行コードは後継の
    目印にならない。→ 改正事由テキストの文法（後継は接続句の後＝そのユニットの最後のコード）
    から old→successor を抽出し、(施行年月日, 改正事由) でユニーク化して重複を畳む。

正規化イベントの契約: old_code / successor_code / year / kind  ← area.events.EVENTS_SCHEMA

安全側の方針（設計＝機械で安全な所＋サジェスト、エッジは人手overrides）:
    後継コードがテキストに明示されない新設（例「柳井市を新設」でコード略）は**出力しない**
    （誤イベントより欠落を選ぶ＝孤児として area-orphans に可視化→overrides で補う）。
    行政区（区の新設/再編）・郡・分割/分離は集約に無関係なので無視する。
"""

import re

import polars as pl

from data_forge.area.events import EVENTS_SCHEMA

_REASON_COL = "改正事由"
_DATE_COL = "廃置分合等施行年月日"

# 括弧内の JIS コード（5桁数字、または末尾英字1の letter 付）。
_CODE = r"[0-9][0-9A-Za-z]{4}"
_PAREN_CODE = re.compile(rf"\(({_CODE})\)")
# 「名前(コード)」ペア。後継コード略記の新設で名前→コードを引くのに使う。
_NAME_CODE = re.compile(rf"([^\s、,，()（）]+?)\(({_CODE})\)")
# 「…（コード）を新設」の後継＝新設ユニットに付いたコード（明示された場合）。
_SHINSETSU_SUCC = re.compile(rf"\(({_CODE})\)を新設")
# コード略記時の新設名（「…C市を新設」の C市）。
_SHINSETSU_NAME = re.compile(r"([^\s、,，()（）]+?)を新設")

# 集約に無関係で、混じっても無視する行（行政区・郡など。編入/合併語を含む行は処理する）。
_IGNORE_TOKENS = ("区の新設", "区の再編", "郡の", "分割", "分離")


def _codes(text: str) -> list[str]:
    return _PAREN_CODE.findall(text)


def _parse_line(line: str) -> list[tuple[str, str, str]]:
    """改正事由の1行から (old_code, successor_code, kind) を抽出する。"""
    if any(tok in line for tok in _IGNORE_TOKENS) and "編入" not in line and "合併" not in line:
        return []
    codes = _codes(line)
    if len(codes) < 2:
        return []

    if "政令指定都市" in line:  # X(old)のY(succ)への政令指定都市施行/移行（年で表記揺れ）
        return [(codes[0], codes[1], "政令指定都市")]

    if "編入" in line:  # A(old)…がB(succ)に編入（旧が複数あり得る）
        *olds, succ = codes
        return [(o, succ, "編入") for o in olds if o != succ]

    if "合併" in line and "新設" in line:  # A(x)、B(y)…が合併し、C(succ)を新設
        m = _SHINSETSU_SUCC.search(line)
        if m:  # 後継コードが明示
            succ = m.group(1)
        else:  # コード略記＝新設名を「名前→コード」で解決（非生存者に当たっても孤児化のみで無害）
            pairs = {n: c for n, c in _NAME_CODE.findall(line)}
            nm = _SHINSETSU_NAME.findall(line)
            succ = pairs.get(nm[-1]) if nm else None
            if succ is None:  # 解決不能＝安全側で欠落（→orphans→overrides）
                return []
        return [(o, succ, "新設合併") for o in codes if o != succ]

    # 名称変更・市制/町制施行・支庁/振興局の区域変更＝いずれもコードが変わる 1→1 の改称系。
    # （境界変更＝部分移管は人口非保存なので対象外。区域変更は非郡の全域移管のみここに来る）
    if any(k in line for k in ("名称変更", "市制施行", "町制施行", "区域変更")):
        old, succ = codes[0], codes[-1]  # A(old)が…C(succ)に …
        return [(old, succ, "改称")] if old != succ else []

    return []


def normalize(raw: pl.DataFrame) -> pl.DataFrame:
    """廃置分合の生CSV DataFrame を正規化イベントへ変換する。"""
    missing = [c for c in (_REASON_COL, _DATE_COL) if c not in raw.columns]
    if missing:
        raise ValueError(
            f"廃置分合CSVに想定列がありません: {missing}。"
            " 実物の列名に合わせて area/history/ingest.py を更新してください。"
        )
    # (施行年月日, 改正事由) でユニーク化＝同一イベントの被影響コード行の重複を畳む
    uniq = raw.select(_DATE_COL, _REASON_COL).unique()

    rows: list[dict] = []
    for date, reason in uniq.iter_rows():
        if reason is None:
            continue
        year = int(str(date)[:4])
        for line in str(reason).splitlines():
            for old, succ, kind in _parse_line(line.strip()):
                rows.append({"old_code": old, "successor_code": succ, "year": year, "kind": kind})

    if not rows:
        return pl.DataFrame(schema=EVENTS_SCHEMA)
    return pl.DataFrame(rows, schema=EVENTS_SCHEMA).unique().sort("year", "old_code")


def parse_history_csv(path, *, encoding: str = "utf8") -> pl.DataFrame:
    """生CSV を読み込み正規化イベントを返す（Shift-JIS の場合 encoding を指定）。"""
    raw = pl.read_csv(path, encoding=encoding, infer_schema_length=0)
    return normalize(raw)
