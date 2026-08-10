# docs

okmethod/data-forge のドキュメント群。

## 構成

| ディレクトリ / ファイル                              | 内容                                                      |
| ---------------------------------------------------- | --------------------------------------------------------- |
| [datasets/data_catalog.md](datasets/data_catalog.md) | データソースの利用規約・商用可否カタログ（e-Stat 等）     |
| [datasets/](datasets/)                               | データセットごとの仕様（statsDataId・出力スキーマ・知見） |

### データセット

| データセット群                                         | 内容                                                          |
| ------------------------------------------------------ | ------------------------------------------------------------- |
| [population](datasets/population.md)                   | 国勢調査 男女別人口（1980〜2020, 単年＋時系列）               |
| [population_by_age](datasets/population_by_age.md)     | 国勢調査 年齢3区分×男女別人口（1980〜2020, 高齢化45年時系列） |
| [daynight_population](datasets/daynight_population.md) | 国勢調査 昼夜間人口（従業地・通学地, 1990〜2020, 7年時系列）  |
| [area_master](datasets/area_master.md)                 | 地域マスタ（アトム軸スタースキーマ）＝合併集約の共有ハブ      |
