# Золотий стандарт форми

З питань стандарту дані всіх форм організації збираються в спільний дашборд. Версія: `2026-06-26-v3`.

| Блок | Питання |
|---|---|
| Місце | `oblast` → `district` → `hromada` → `settlement`: кожен список фільтрує наступний |
| Людина | `date_of_birth` (дата), `gender` (`man`, `woman`) |
| Родина | `military_veteran_family` (`yes`, `no`) |
| Склад домогосподарства | `boys_0_17`, `girls_0_17`, `men_18_59`, `women_18_59`, `men_60_plus`, `women_60_plus` і до кожного «З них …»: ВПО, інвалідність, діти чи сім'ї військових, ветеранів, загиблих, зниклих, полонених |
| Підсумок | `household_size`, `low_income` (`yes`, `no`) |

## Правила

1. Можна взяти всі питання стандарту або частину, але кожне — без змін: та сама технічна назва, тип,
   підпис, підказка, обмеження, список і коди варіантів. Копіюй рядки з вмісту нижче як є.
2. Місце — усі чотири рівні разом. Питання «З них …» — лише разом із загальним питанням своєї групи.
3. Питання стандарту не клади в групи: у групі `oblast` стає в даних `group/oblast`, і дашборд його не знайде.
4. Списки місць у стандарті — лише зразок. Додай місця, де працює проєкт, у ті самі списки з тими самими
   колонками-фільтрами. Код місця, яке вже є в інших формах, бери звідти до літери. Новий код — латиницею,
   малими літерами, як у зразку: `lvivska`, `lviv_district`, `lviv_hromada`, `lviv`.

## Що вважати відхиленням

- у формі немає жодного питання стандарту;
- питання стандарту змінене чи стоїть у групі, або з блоку взято лише частину (правила 1–3);
- те саме запитано по-своєму: вік числом замість дати народження, стать з іншими варіантами, місце
  текстом чи іншим списком, ВПО чи інвалідність «так/ні» замість кількості, розмір родини під іншою назвою.

## Вміст стандарту

```json
{
  "survey": [
    {"type": "select_one", "select_from_list_name": "oblast", "name": "oblast", "label": ["Область"], "required": true},
    {"type": "select_one", "select_from_list_name": "district", "name": "district", "label": ["Район"], "required": true, "choice_filter": "oblast=${oblast}"},
    {"type": "select_one", "select_from_list_name": "hromada", "name": "hromada", "label": ["Громада"], "required": true, "choice_filter": "district=${district}"},
    {"type": "select_one", "select_from_list_name": "settlement", "name": "settlement", "label": ["Населений пункт"], "required": true, "choice_filter": "hromada=${hromada}"},
    {"type": "date", "name": "date_of_birth", "label": ["Дата народження"], "required": true},
    {"type": "select_one", "select_from_list_name": "gender", "name": "gender", "label": ["Стать"], "required": true},
    {"type": "select_one", "select_from_list_name": "yesno", "name": "military_veteran_family", "label": ["Чи є в родині військовослужбовці або ветерани?"], "required": true},
    {"type": "integer", "name": "boys_0_17", "label": ["Кількість хлопців 0–17 років у домогосподарстві"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "idp_boys_0_17", "label": ["З них хлопців 0–17 років зі статусом ВПО"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "disability_boys_0_17", "label": ["З них хлопців 0–17 років з інвалідністю"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "orphan_boys_0_17", "label": ["З них хлопців 0–17 років, які втратили одного або обох батьків"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "service_member_boys_0_17", "label": ["З них хлопців 0–17 років — дітей військовослужбовця"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "veteran_boys_0_17", "label": ["З них хлопців 0–17 років — дітей ветерана війни"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "fallen_warrior_boys_0_17", "label": ["З них хлопців 0–17 років — дітей загиблого/загиблої воїна"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "missing_soldier_boys_0_17", "label": ["З них хлопців 0–17 років — дітей безвісти зниклого воїна"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "captivity_soldier_boys_0_17", "label": ["З них хлопців 0–17 років — дітей воїна в полоні"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "girls_0_17", "label": ["Кількість дівчат 0–17 років у домогосподарстві"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "idp_girls_0_17", "label": ["З них дівчат 0–17 років зі статусом ВПО"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "disability_girls_0_17", "label": ["З них дівчат 0–17 років з інвалідністю"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "orphan_girls_0_17", "label": ["З них дівчат 0–17 років, які втратили одного або обох батьків"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "service_member_girls_0_17", "label": ["З них дівчат 0–17 років — дітей військовослужбовця"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "veteran_girls_0_17", "label": ["З них дівчат 0–17 років — дітей ветерана війни"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "fallen_warrior_girls_0_17", "label": ["З них дівчат 0–17 років — дітей загиблого/загиблої воїна"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "missing_soldier_girls_0_17", "label": ["З них дівчат 0–17 років — дітей безвісти зниклого воїна"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "captivity_soldier_girls_0_17", "label": ["З них дівчат 0–17 років — дітей воїна в полоні"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "men_18_59", "label": ["Кількість чоловіків 18–59 років у домогосподарстві"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "idp_men_18_59", "label": ["З них чоловіків 18–59 років зі статусом ВПО"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "disability_men_18_59", "label": ["З них чоловіків 18–59 років з інвалідністю"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "service_member_family_men_18_59", "label": ["З них чоловіків 18–59 років із сімей військовослужбовиць"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "veteran_family_men_18_59", "label": ["З них чоловіків 18–59 років із сімей ветеранок війни"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "fallen_warrior_family_men_18_59", "label": ["З них чоловіків 18–59 років із сімей загиблих військовослужбовиць"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "missing_soldier_family_men_18_59", "label": ["З них чоловіків 18–59 років із сімей безвісти зниклих військовослужбовиць"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "captivity_soldier_family_men_18_59", "label": ["З них чоловіків 18–59 років із сімей військовослужбовиць у полоні"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "women_18_59", "label": ["Кількість жінок 18–59 років у домогосподарстві"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "idp_women_18_59", "label": ["З них жінок 18–59 років зі статусом ВПО"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "disability_women_18_59", "label": ["З них жінок 18–59 років з інвалідністю"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "service_member_family_women_18_59", "label": ["З них жінок 18–59 років із сімей військовослужбовців"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "veteran_family_women_18_59", "label": ["З них жінок 18–59 років із сімей ветеранів війни"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "fallen_warrior_family_women_18_59", "label": ["З них жінок 18–59 років із сімей загиблих військовослужбовців"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "missing_soldier_family_women_18_59", "label": ["З них жінок 18–59 років із сімей безвісти зниклих військовослужбовців"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "captivity_soldier_family_women_18_59", "label": ["З них жінок 18–59 років із сімей військовослужбовців у полоні"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "men_60_plus", "label": ["Кількість чоловіків 60+ років у домогосподарстві"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "idp_men_60_plus", "label": ["З них чоловіків 60+ років зі статусом ВПО"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "disability_men_60_plus", "label": ["З них чоловіків 60+ років з інвалідністю"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "service_member_family_men_60_plus", "label": ["З них чоловіків 60+ років із сімей військовослужбовиць"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "veteran_family_men_60_plus", "label": ["З них чоловіків 60+ років із сімей ветеранок війни"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "fallen_warrior_family_men_60_plus", "label": ["З них чоловіків 60+ років із сімей загиблих військовослужбовиць"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "missing_soldier_family_men_60_plus", "label": ["З них чоловіків 60+ років із сімей безвісти зниклих військовослужбовиць"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "captivity_soldier_family_men_60_plus", "label": ["З них чоловіків 60+ років із сімей військовослужбовиць у полоні"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "women_60_plus", "label": ["Кількість жінок 60+ років у домогосподарстві"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "idp_women_60_plus", "label": ["З них жінок 60+ років зі статусом ВПО"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "disability_women_60_plus", "label": ["З них жінок 60+ років з інвалідністю"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "service_member_family_women_60_plus", "label": ["З них жінок 60+ років із сімей військовослужбовців"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "veteran_family_women_60_plus", "label": ["З них жінок 60+ років із сімей ветеранів війни"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "fallen_warrior_family_women_60_plus", "label": ["З них жінок 60+ років із сімей загиблих військовослужбовців"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "missing_soldier_family_women_60_plus", "label": ["З них жінок 60+ років із сімей безвісти зниклих військовослужбовців"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "captivity_soldier_family_women_60_plus", "label": ["З них жінок 60+ років із сімей військовослужбовців у полоні"], "hint": ["Якщо немає таких осіб, вкажіть 0."], "required": true, "constraint": ". >= 0", "constraint_message": ["Введіть 0 або більше."]},
    {"type": "integer", "name": "household_size", "label": ["Загальна кількість членів домогосподарства"], "required": true, "constraint": ". >= 1", "constraint_message": ["Вкажіть кількість членів домогосподарства від 1."]},
    {"type": "select_one", "select_from_list_name": "yesno", "name": "low_income", "label": ["Чи є домогосподарство малозабезпеченим / економічно незахищеним?"], "hint": ["Дохід менше 6318 грн на місяць на 1 члена домогосподарства."], "required": true}
  ],
  "choices": [
    {"list_name": "oblast", "name": "lvivska", "label": ["Львівська область"]},
    {"list_name": "district", "name": "lviv_district", "label": ["Львівський район"], "oblast": "lvivska"},
    {"list_name": "hromada", "name": "lviv_hromada", "label": ["Львівська громада"], "district": "lviv_district"},
    {"list_name": "hromada", "name": "solonka_hromada", "label": ["Солонківська громада"], "district": "lviv_district"},
    {"list_name": "settlement", "name": "lviv", "label": ["Львів"], "hromada": "lviv_hromada"},
    {"list_name": "settlement", "name": "zubra", "label": ["Зубра"], "hromada": "solonka_hromada"},
    {"list_name": "gender", "name": "man", "label": ["Чоловік"]},
    {"list_name": "gender", "name": "woman", "label": ["Жінка"]},
    {"list_name": "yesno", "name": "yes", "label": ["Так"]},
    {"list_name": "yesno", "name": "no", "label": ["Ні"]}
  ],
  "settings": {},
  "translations": [null],
  "translated": ["constraint_message", "hint", "label"]
}
```
