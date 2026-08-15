"""e-Stat ソース層（取得 → tidy 化 → 表固有クレンジングの段）。

日本政府統計ポータル e-Stat の getStatsData を唯一のソースとする取得・整形層。

    client.py    … REST API の薄いクライアント（appId 注入・NEXT_KEY ページング吸収）
    fetch.py     … 生レスポンスの取得と data/raw/estat/ へのキャッシュ
    transform.py … CLASS_INF + DATA_INF のスタースキーマを tidy な DataFrame へ、
                    出典メタ・area 階層の抽出
    population.py / age5.py / daynight.py / households.py … 各表固有のクレンジング（cleaner）

cleaner は datasets.py が各データセット定義へ束ね、共通の取得/tidy を経て呼ばれる。
アトム抽出など area 表現に依存する処理は本層の tidy 出力を area 層が引き取る。
"""
