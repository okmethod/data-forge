# docs

okmethod/data-forge のドキュメント群。

## 構成

| ディレクトリ / ファイル                              | 内容                                                      |
| ---------------------------------------------------- | --------------------------------------------------------- |
| [datasets/data_catalog.md](datasets/data_catalog.md) | データソースの利用規約・商用可否カタログ（e-Stat 等）     |
| [datasets/](datasets/)                               | データセットごとの仕様（statsDataId・出力スキーマ・知見） |

### データセット

| データセット群                                         | 内容                                                                                               |
| ------------------------------------------------------ | -------------------------------------------------------------------------------------------------- |
| [population](datasets/population.md)                   | 国勢調査 男女別人口（市区町村 1980〜2020＋2025速報／都道府県 世紀 companion 1920〜2020）           |
| [population_by_age](datasets/population_by_age.md)     | 国勢調査 年齢3区分×男女別人口（市区町村 1980〜2020／都道府県 世紀 companion 1920〜2020・総数）     |
| [population_by_age5](datasets/population_by_age5.md)   | 国勢調査 年齢5歳階級×男女別人口（市区町村 2010〜2020＝旗艦／全国・都道府県 1920〜2020＝companion） |
| [daynight_population](datasets/daynight_population.md) | 国勢調査 昼夜間人口（従業地・通学地, 1990〜2020, 7年時系列）                                       |
| [households](datasets/households.md)                   | 国勢調査 世帯の種類別 世帯数・世帯人員（全国・都道府県, 1960〜2020）                               |
| [family_type](datasets/family_type.md)                 | 国勢調査 世帯の家族類型16区分別 世帯数・世帯人員（全国・都道府県, 1995〜2020, 単独世帯割合）       |
| [labor_force](datasets/labor_force.md)                 | 国勢調査 労働力状態3区分×男女別人口（全国・都道府県, 1950〜2020）                                  |
| [industry](datasets/industry.md)                       | 国勢調査 産業大分類×男女別就業者数（全国1995〜/都道府県2005〜2020）                                |
| [occupation](datasets/occupation.md)                   | 国勢調査 職業大分類×男女別就業者数（major12=12区分1995〜/major10=10区分・全国1950〜/県1980〜2005） |
| [area_master](datasets/area_master.md)                 | 地域マスタ（アトム軸スタースキーマ）＝合併集約の共有ハブ                                           |
