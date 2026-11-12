# Следующие шаги

1. Сохранять в отчётах версию Ensembl VEP/release и параметры запроса; добавить опциональную аннотацию ClinVar с allele-condition-transcript сопоставлением.
2. Загрузить версионированные HPO ontology и disease annotations, считать семантическое сходство по графу и учитывать frequency/age только при наличии данных.
3. Создать reviewable allele-condition-transcript evidence table с HGVS/ALT точным сопоставлением, ClinVar Variation ID, disease ID, review stars, last evaluated date и primary literature.
4. Добавить семейные данные, segregation, de novo evidence и фазировку; отсутствие этих сведений не заменять предположениями.
5. Добавить независимые development/test cases; не оптимизировать и не публиковать метрики на обучающих/полусинтетических данных как клиническую точность.
6. Только после достаточной валидации рассматривать калибровку вероятностей. До этого показывать только ranking score.
