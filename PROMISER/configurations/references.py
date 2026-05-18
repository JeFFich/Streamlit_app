"""
Справочники, нужные предсказателю помимо словарей DTB / SOV / value / trp_cost / CE.

CLOSEST_START_RK — для каждой бизнес-категории (`category` в data_to_predict)
                   список исторических флайтов, по которым калибруем
                   final_coeff (find_fin_coeff). Обновлять при появлении новых
                   завершённых кампаний.
"""

CLOSEST_START_RK: dict[str, list[str]] = {
    "CC-Test": [
        "Avito_Goods_gc-24-01-02-TRX-Buyer-Protection-T1-C2C",
        "Avito_Goods_gc-24-09-AvitoMall+T&S-T1",
        "Avito_Goods_gc-26-03-CC-Resale-T1-C2C"
    ],
    "HL-Construction": [
        "Avito_Goods_gc-24-06-H&L-T1-Construction-SALE",
        "Avito_Goods_gc-24-04-HL-Construction-XY-T1-C2C",
        "Avito_Goods_gc-25-04-H&L-T1-Construction",
        "Avito_Goods_gc-25-07-H&L-T1-Construction",
    ],
    "HL-Furniture": [
        "Avito_Goods_gc-24-10-HL-Furniture-Feature-C2C",
        "Avito_Goods_gc-25-10-HL-Furniture-Loans-T1-C2C",
    ],
    "SP-SpareParts": [
        "Avito_Goods_gc-24-05-SP-RoadTrips-T1-C2C",
        "Avito_Goods_gc-24-02-03-SP-maintenance-SP-T1-C2C",
        "Avito_Goods_gc-25-01-SP-Garage-2-T1-2C",
        "Avito_Goods_gc-24-07-SP-Garage-win-a-car-SP-T1-2C",
        "Avito_Goods_gc-25-05-SP-First car & first repair-T1-2C",
    ],
    "SP-Tires": [
        "Avito_Goods_gc-24-10-SP-WinterTires-T1-2C",
        "Avito_Goods_gc-24-03-04-SP-Summer-tires-T1-C2C",
        "Avito_Goods_gc-25-10-SP-Winter Tires & Service-T1-2C",
    ],
    "Sale": [
        "Avito_Goods_gc-24-11-СС-November-BIG-SALE-T1",
        "Avito_Goods_gc-24-06-СС-SALE-Federal",
        "Avito_Goods_gc-24-12-EL&LS-SALE-T1",
        "Avito_Goods_gc-25-02-CC-Gender",
        "Avito_Goods_gс-25-11-CC-November-BIG-SALE-T1-2C",
        "Avito_Goods_gc-25-12-CC-New-Year-SALE-T1-2C",
        "Avito_Goods_gc-25-08-CC-Back-to-school-SALE-T1-2C",
        "Avito_Goods_gc-26-02-CC-Gender-T1"
    ],
    "EL": [
        "Avito_Goods_gc-24-02-EL-GenderHolidays-T1-C2C",
        "Avito_Goods_gc-24-12-EL&LS-SALE-T1",
    ],
    "LS-Fashion": [
        "Avito_Goods_gc-24-09-AvitoMall+T&S-T1",
        "Avito_Goods_gc-24-06-СС-SALE-Federal",
        "Avito_Goods_gc-25-03-LS-Fashion-T1-C2C"
    ],
    "JobsCore": [
        "Avito_Job_jc-24-08-General-Better_Matching_on_Avito-T1-B2C",
        "Avito_Job_jc-24-01-General-Find_your_place-T1-B2C",
        "Avito_Job_jc-24-06-General-Off_season-T1-B2C",
        "Avito _Job_jc-24-03-General-Find_your_place-T1-B2C",
        "Avito_Job_jc-25-01-General-T1-B2C",
        "Avito_Job_jc-25-05-General-Off_Season-T1-B2C",
        "Avito_Job_jc-25-08-General-T1-B2C",
        "Avito_Job_jc-26-01-General-T1-B2C"
    ],
    "RRE": [
        "Avito_RE_re-24-01-ND_SS-RRE_янв-апр-T1-С2С",
        "Avito_RE_ re-24-09-RRE_сент-ноя-T1-С2С",
        "Avito_RE_re-25-01-RRE_янв-март-T1-С2С",
        "Avito_RE_re-25-08-RRE_авг-ноя-T1-С2С",
        "Avito_RE_re-26-01-RRE_янв-мар-T1-С2С"
    ],
    "Rent": [
        "Avito_RE_re-24-10-STR-окт-дек-T1-С2С",
        "Avito_RE_re-24-04-STR-T1-С2С",
        "Avito_RE_re-25-04-STR_апр-авг-T1-С2C",
        "Avito_RE_re-25-10-STR_окт-дек-T1-С2C"
    ],
    "LTR": [
        "Avito_RE_re-24-08-LTR-авг-сент-T1-С2С",
    ],
    "Appliances": [
        "Avito_Services_se_24-03-CROSS_MR&AP-T1-С2С",
        "Avito Services_se_25-05-AP-T1-C2C"
    ],
    "MajorRepair": [
        "Avito_Services_se_24-03-CROSS_MR&AP-T1-С2С",
        "Avito_Services_se_24-08-CROSS_MR&TR-T1-С2С",
        "Avito Services_se_25-04-MR -T1-C2C",
        "Avito Services_se_25-08-MR-T1-C2C"
    ],
    "Household": [
        "Avito_Services_se_24-06-HH-T1-С2С",
        "Avito Services_se_25-07-HH -T1-C2C"
    ],
    "Transportation": [
        "Avito_Services_se_24-08-CROSS_MR&TR-T1-С2С",
        "Avito Services_se_25-08-TR-T1-C2C"
    ],
    "HealthAndBeauty": [
        "Avito Services_se_25-11-H&B -T1-C2C"    
    ],
    "Cars": [
        "Avito_Auto_au-24-03-UCB-Buyers-T1-C2C",
        "Avito_Auto_au-24-09-SL-Select-T1-C2C",
    ],
    "Sellers": [
        "Avito_Goods_gc-25-07-Sellers-cross-private-T1-B2C"
    ],
    "AvitoAll": [
        "Avito_Horizontal_hz-25-04-CC-Manifest-T1-C2"
    ]
}


# ---------------------------------------------------------------------------
# Reference-флайты по вертикалям (для slim-промисера)
# ---------------------------------------------------------------------------
# Используются, когда у нас новый «кастомный» разрез без истории флайтов:
# берём reference-РК из вертикали, к которой относится первый логкат разреза.
# Списки — конкатенация подходящих категорий из CLOSEST_START_RK выше.
# Gigs.* мэпим в Vacancies&Gigs (вертикаль Jobs).
VERTICAL_REFERENCE_FLIGHTS: dict[str, list[str]] = {
    "Goods": (
        CLOSEST_START_RK["CC-Test"]
        + CLOSEST_START_RK["HL-Construction"]
        + CLOSEST_START_RK["HL-Furniture"]
        + CLOSEST_START_RK["SP-SpareParts"]
        + CLOSEST_START_RK["SP-Tires"]
        # + CLOSEST_START_RK["Sale"]
        + CLOSEST_START_RK["EL"]
        + CLOSEST_START_RK["LS-Fashion"]
    ),
    "Services": (
        CLOSEST_START_RK["Appliances"]
        + CLOSEST_START_RK["MajorRepair"]
        + CLOSEST_START_RK["Household"]
        #+ CLOSEST_START_RK["Transportation"]
        + CLOSEST_START_RK["HealthAndBeauty"]
    ),
    "Transport": CLOSEST_START_RK["Cars"],
    "Realty&Travel": (
        CLOSEST_START_RK["RRE"]
        + CLOSEST_START_RK["LTR"]
    ),
    "Travel": CLOSEST_START_RK["Rent"],
    "Vacancies&Gigs": CLOSEST_START_RK["JobsCore"],
    "Horizontal": CLOSEST_START_RK["AvitoAll"]
}
