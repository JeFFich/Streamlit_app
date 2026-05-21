"""
Класс с кучей конфигов для настройки виджетов
"""

# ID гугл-таблицы, куда записываются состояния сессий у пользователей
CONFIG_SHEET_ID = "1jwE4I7fnWfqkOT6TMtY_8piACgfGYT3X8yQXJyQaXuw"

# Список месяцев
DEFAULT_MONTHS = ["Январь", "Февраль", "Март", "Апрель", "Май", "Июнь", "Июль", "Август", "Сентябрь", "Октябрь", "Ноябрь", "Декабрь"]

# Поправка выручки
BUDGET_COEFF_CORRECTRION = 1.3

# Логкаты по вертикалям
LOGICAL_CATEGORIES = {
    'Horizontal': [
        'Goods.TiresAndWheels',
        'Goods.Telecom',
        'Goods.Sports',
        'Goods.SpecializedEquipment',
        'Goods.SparePartsServices',
        'Goods.SpareParts',
        'Goods.InformationTechnology',
        'Goods.IndustrialEquipment',
        'Goods.HomeAndGarden',
        'Goods.Hobby',
        'Goods.HealthAndBeauty',
        'Goods.GoodsForPets',
        'Goods.GoodsForChildren',
        'Goods.Furniture',
        'Goods.FoodTradeEquipment',
        'Goods.Food',
        'Goods.Fashion',
        'Goods.DomesticAppliances',
        'Goods.ConstructionRenovation',
        'Goods.CommtransSpareParts',
        'Goods.Business',
        'Goods.AudioVideo',
        'Goods.Animals',
        'Transport.CarRentals',
        'Transport.UsedMachinery',
        'Transport.MachineryRentals',
        'Transport.NewCars',
        'Transport.UsedCars',
        'Transport.Moto',
        'Transport.NewMachinery',
        'Transport.Water',
        'Services.TransportationAndDelivery',
        'Services.Training',
        'Services.PassengerTransportation',
        'Services.MinorRepair',
        'Services.MajorRepair',
        'Services.Machinery',
        'Services.Household',
        'Services.HealthAndBeauty',
        'Services.EventsAndEntertainment',
        'Services.Evacuation',
        'Services.CargoTransportation',
        'Services.Business',
        'Services.Appliances',
        'Realty.Suburban',
        'Realty.NewDevelopments',
        'Realty.Foreign',
        'Realty.SecondarySell',
        'Realty.LongRent',
        'Realty.Commercial',
        'Travel.Rent',
        'Travel.ShortRent',
        'Vacancies.Office',
        'Vacancies.TaxiRentals',
        'Vacancies.ManualAndLinear',
        'Vacancies.TaxiTransportLogistics',
        'Gigs.Retail'
    ],
    'Goods': [
        'Goods.TiresAndWheels',
        'Goods.Telecom',
        'Goods.Sports',
        'Goods.SpecializedEquipment',
        'Goods.SparePartsServices',
        'Goods.SpareParts',
        'Goods.InformationTechnology',
        'Goods.IndustrialEquipment',
        'Goods.HomeAndGarden',
        'Goods.Hobby',
        'Goods.HealthAndBeauty',
        'Goods.GoodsForPets',
        'Goods.GoodsForChildren',
        'Goods.Furniture',
        'Goods.FoodTradeEquipment',
        'Goods.Food',
        'Goods.Fashion',
        'Goods.DomesticAppliances',
        'Goods.ConstructionRenovation',
        'Goods.CommtransSpareParts',
        'Goods.Business',
        'Goods.AudioVideo',
        'Goods.Animals'
    ],
    'Transport': [
        'Transport.CarRentals',
        'Transport.UsedMachinery',
        'Transport.MachineryRentals',
        'Transport.NewCars',
        'Transport.UsedCars',
        'Transport.Moto',
        'Transport.NewMachinery',
        'Transport.Water'
    ],
    'Services': [
        'Services.TransportationAndDelivery',
        'Services.Training',
        'Services.PassengerTransportation',
        'Services.MinorRepair',
        'Services.MajorRepair',
        'Services.Machinery',
        'Services.Household',
        'Services.HealthAndBeauty',
        'Services.EventsAndEntertainment',
        'Services.Evacuation',
        'Services.CargoTransportation',
        'Services.Business',
        'Services.Appliances'
    ],
    'Realty': [
        'Realty.Suburban',
        'Realty.NewDevelopments',
        'Realty.Foreign',
        'Realty.SecondarySell',
        'Realty.LongRent',
        'Realty.Commercial',
    ],
    'Travel': [
        'Travel.Rent',
        'Travel.ShortRent'
    ],
    'Jobs': [
        'Vacancies.Office',
        'Vacancies.TaxiRentals',
        'Vacancies.ManualAndLinear',
        'Vacancies.TaxiTransportLogistics'
    ],
    'Gigs': [
        'Gigs.Retail'
    ]
}

# Настройки по TRP
MIN_TRP = 0
MAX_TRP = 5500
DEF_TRP = 1500
STEP_TRP = 250

# Настройки по SOV
MIN_SOV = 0.0
MAX_SOV = 1.00
DEF_SOV = 0.13
STEP_SOV = 0.01

# Настройки по ROMI
MIN_ROMI = -100
MAX_ROMI = -70
DEF_ROMI = -90
STEP_ROMI = 1

# Настройки по числу РК
MIN_RK = 0
MAX_RK = 4
DEF_RK_MIN = 1
DEF_RK_MAX = 2
STEP_RK = 1

# Настройки по бюджету
MIN_BUDG = 0
MAX_BUDG = 3000
DEF_BUDG_MIN = 150
DEF_BUDG_MAX = 600
STEP_BUDG = 100

# Настройки по длительности РК
MIN_LEN = 0
MAX_LEN = 4
DEF_LEN_MIN = 1
DEF_LEN_MAX = 2
STEP_LEN = 1

# Настройки по максимальному бюджету на вертикаль
MIN_VERT_BUDG = 0
MAX_VERT_BUDG = 4500
STEP_VERT_BUDG = 100
DEF_VERT_BUDG = 1000

# Настройки по минимальному TRP на вертикаль
MIN_VERT_TRP = 0
MAX_VERT_TRP = 10000
STEP_VERT_TRP = 250
DEF_VERT_TRP = 6000

# Настройки по минимальному числу РК на вертикаль
MIN_VERT_RK_MIN = 0
MAX_VERT_RK_MIN = 7
STEP_VERT_RK_MIN = 1
DEF_VERT_RK_MIN = 2

# Настройки по максимальному числу РК на вертикаль
MIN_VERT_RK_MAX = 0
MAX_VERT_RK_MAX = 20
STEP_VERT_RK_MAX = 1
DEF_VERT_RK_MAX = 4

# Список пресетов категорий по вертикалям
PRESETS_BY_VERTICAL = {
    "Transport": [
        {'category_name': 'Cars', 'logical_category': ['Transport.NewCars', 'Transport.UsedCars']}
    ],
    "Realty": [
        {'category_name': 'RRE', 'logical_category': ['Realty.LongRent', 'Realty.SecondarySell', 'Realty.NewDevelopments']},
        {'category_name': 'LTR', 'logical_category': ['Realty.LongRent']}
    ],
    "Travel": [
        {'category_name': 'Rent', 'logical_category': ['Travel.ShortRent', 'Travel.Rent']}
    ],
    "Services": [
        {'category_name': 'MajorRepair', 'logical_category': ['Services.MajorRepair']},
        # {'category_name': 'Transportation', 'logical_category': ['Services.TransportationAndDelivery']},
        {'category_name': 'HealthAndBeauty', 'logical_category': ['Services.HealthAndBeauty']},
        {'category_name': 'Appliances', 'logical_category': ['Services.Appliances']},
        {'category_name': 'Household', 'logical_category': ['Services.Household']}
    ],
    "Goods": [
        {'category_name': 'Sale', 'logical_category': LOGICAL_CATEGORIES["Goods"]},
        {'category_name': 'CC-Test', 'logical_category': LOGICAL_CATEGORIES["Goods"]},
        {'category_name': 'HL-Furniture', 'logical_category': ['Goods.Furniture']},
        {'category_name': 'HL-Construction', 'logical_category': ['Goods.ConstructionRenovation']},
        {'category_name': 'EL', 'logical_category': ['Goods.AudioVideo', 'Goods.DomesticAppliances', 'Goods.InformationTechnology', 'Goods.Telecom']},
        {'category_name': 'LS-Fashion', 'logical_category': ['Goods.Fashion']},
        {'category_name': 'SP-SpareParts', 'logical_category': ['Goods.SpareParts', 'Goods.SparePartsServices']},
        {'category_name': 'SP-Tires', 'logical_category': ['Goods.TiresAndWheels']}
    ],
    "Jobs": [
        {'category_name': 'JobsCore', 'logical_category': ['Vacancies.ManualAndLinear']}
    ],
    "Gigs": [
        {'category_name': 'Retail', 'logical_category': ['Gigs.Retail']}
    ],
    "Horizontal": [
        {'category_name': 'AvitoAll', 'logical_category': LOGICAL_CATEGORIES["Horizontal"]}
    ]
}
