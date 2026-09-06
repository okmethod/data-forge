"""population 母集団の family 群（docs 順に公開）。"""

from data_forge.datasets.population import (
    age3class,
    age5year,
    daynight,
    labor_force,
    population,
)

SUBREGISTRIES = (
    population.DATASETS,
    age3class.DATASETS,
    age5year.DATASETS,
    daynight.DATASETS,
    labor_force.DATASETS,
)
