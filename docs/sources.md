# Data Sources (data_sources table)

| id | Source | Used for | Year | Licence | URL / DOI | Status |
|---|---|---|---|---|---|---|
| S1 | South Asia Indoor Heat dataset (Tasgaonkar et al. 2022, *Scientific Data* 9:285) | Delhi indoor−outdoor offsets by roof and floor | 2016 | CC0 | https://doi.org/10.6084/m9.figshare.12546368.v1 · paper https://www.nature.com/articles/s41597-022-01314-5 | Downloaded, checked |
| S2 | Census 2011 HL-02A, households by roof material, NCT of Delhi | District/town roof prior | 2011 (old) | GODL-India | https://censusindia.gov.in/nada/index.php/catalog/7860 | Downloaded, checked |
| S3 | NFHS-5 Household Recode (hv215 roof) | Roof prior (newer) | 2019–21 | DHS terms (registration) | https://dhsprogram.com | Pending: team registration |
| S4 | NSS 76th round, Delhi state report (DES Delhi) | Housing context (pucca, flats, ventilation) | 2018 | Govt publication | https://des.delhi.gov.in/sites/default/files/survey_on_drinking_water_sanititation_hygiene_and_housing_condition.pdf | Downloaded, checked |
| S5 | Delhi Heat Action Plan 2024-25 (DDMA) | Alert levels, hotspot wards (context) | 2024 | Govt publication | https://ddma.delhi.gov.in/sites/default/files/ddma/generic_multiple_files/hap_6.05.2024.pdf | Downloaded, checked |
| S6 | Building footprints: Google Open Buildings v3 / Microsoft / OSM / Overture | Tap-to-select, density | 2023–26 | CC BY 4.0 / ODbL | (Phase 2) | Not yet measured |
| S7 | ERA5-Land hourly via Open-Meteo archive API | Weather history, 2021-2026; p97 2008-2019 | 2008-2026 | Free non-commercial, attribution (Open-Meteo); ERA5 Copernicus licence | https://open-meteo.com/en/docs/historical-weather-api | Downloaded; validated vs 2016 AWS |
| S8 | Open-Meteo forecast API | Live status, 7-day | live | Free non-commercial, attribution | https://open-meteo.com/en/docs | Tested |
| S9 | Landsat 8/9 Collection 2 Level-2 (USGS) via Microsoft Planetary Computer | Day surface heat, 30 m | Apr-Jun 2021-2026 (84 scenes) | Public domain | https://planetarycomputer.microsoft.com/dataset/landsat-c2-l2 | Composite built |
| S10 | MODIS MYD11A2 v061 LST_Night_1km (NASA LP DAAC) via Planetary Computer | Night surface heat | Apr-Jun 2021-2026 | Public domain | https://planetarycomputer.microsoft.com/dataset/modis-11A2-061 | Composite built |
| S11 | ESA WorldCover 10 m v200 | Land cover fractions | 2021 | CC BY 4.0 | https://planetarycomputer.microsoft.com/dataset/esa-worldcover | Done |
| S12 | WorldPop Global2 R2025A 1 km constrained (UN-adj.), total + age 0, 1-4, 65-90 (all India) | Population, 65+ and under-5 per Delhi ward and per Indian district | 2025 | CC BY 4.0 | https://hub.worldpop.org/geodata/listing?id=135 | Done (age shares low-information) |
| S13 | DataMeet Municipal_Spatial_Data - Delhi wards (pre-2022) | Ward units | pre-2022 | CC BY-SA 2.5 IN | https://github.com/datameet/Municipal_Spatial_Data/tree/master/Delhi | Done (old delimitation) |
| S14 | geoBoundaries IND ADM2 (source: Local Government Directory, Govt of India) | District polygons for all India (735 units; outline follows India's official boundary) | 2021 | ODbL 1.0 | https://www.geoboundaries.org | Done |
| S15 | DUSIB Directory - Index/Summary of assets | JJ clusters per district | 2022 | Govt publication | https://delhishelterboard.in/main/wp-content/uploads/2022/06/Directory_of_DUSIB.pdf | Done (counts only) |
| S16 | NFHS-5 Delhi state report FR374 (IIPS/ICF) | AC/cooler 74.3 %, fan 98.2 %, pucca 93.7 % | 2019-21 | Public report | https://dhsprogram.com/pubs/pdf/FR374/FR374_Delhi.pdf | Done |
| S17 | NWS heat index equation; Stull 2011 wet-bulb | Formulas | — | Public | https://www.wpc.ncep.noaa.gov/html/heatindex_equation.shtml ; doi:10.1175/JAMC-D-11-0143.1 | Implemented + tested |
| S18 | GeoNames postal codes (IN) + all-India place names + admin codes | Offline place naming, PIN / place search (no third-party geocoder at runtime) | downloaded 2026-10-15 | CC BY 4.0 | https://download.geonames.org/export/zip/IN.zip ; https://download.geonames.org/export/dump/IN.zip | Done (PIN coordinates unreliable in cities -> PIN not shown for GPS points) |
| S19 | Open-Meteo historical weather API (ECMWF ERA5 / ERA5-Land reanalysis) daily Tmax, Tmin, max wet-bulb | District summer heat (1 Apr-30 Jun, 2021-2025) | 2021-2025 | CC BY 4.0 (Open-Meteo), Copernicus licence (ERA5) | https://open-meteo.com/en/docs/historical-weather-api | Done |
