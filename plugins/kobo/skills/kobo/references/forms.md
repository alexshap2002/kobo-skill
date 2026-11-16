# Форми: як скласти, створити й безпечно змінити

## Зміст
1. Формат вмісту форми
2. Типи питань
3. Умови, обмеження, обчислення
4. Групи й повторювані групи
5. Кілька мов
6. Зміна наявної форми

## 1. Формат вмісту форми

Питання про місце, вік, стать і склад домогосподарства бери із золотого стандарту (`standard.md`).

Вміст форми (`content`) має ті самі колонки, що й XLSForm: аркуші `survey`, `choices` і `settings`. Kobo
приймає його у своєму рідному вигляді:
- підписи (`label`, `hint`, `constraint_message`) — це списки, по одному тексту на кожну мову:
  `"label": ["Текст"]`;
- для вибору тип і список пишуться окремо: `"type": "select_one"`, `"select_from_list_name": "oblast"`;
- групи пишуться через підкреслення: `begin_group`, `end_group`, `begin_repeat`, `end_repeat`;
- `"translations": [null]` для однієї мови;
- `"translated"` — назви колонок, які задано списками.

Кожна колонка-список (`label`, `hint`, `constraint_message`, `required_message`…) має бути в
`translated`, і в кожному списку рівно стільки текстів, скільки мов у `translations`. Інакше Kobo додасть
зайву «мову» без назви.

Під час збереження Kobo вміст не перевіряє: помилки з'являться лише при розгортанні. Тому перед
відправкою перевір сам, що:
- технічні назви не повторюються;
- для кожного `select_*` і `rank` є список варіантів (`select_from_list_name`);
- кожну групу закрито.

```json
{
  "survey": [
    {"type": "start", "name": "start"},
    {"type": "end", "name": "end"},
    {"type": "text", "name": "full_name", "label": ["Прізвище та ім'я"], "required": true},
    {"type": "integer", "name": "visits", "label": ["Скільки разів відвідували заняття?"], "constraint": ". >= 0",
     "constraint_message": ["Введіть 0 або більше"]},
    {"type": "select_multiple", "select_from_list_name": "needs", "name": "needs", "label": ["Потреби"]},
    {"type": "text", "name": "needs_other", "label": ["Інше — що саме?"],
     "relevant": "selected(${needs}, 'other')"},
    {"type": "acknowledge", "name": "consent", "label": ["Згода на обробку персональних даних"],
     "required": true}
  ],
  "choices": [
    {"list_name": "needs", "name": "food", "label": ["Харчування"]},
    {"list_name": "needs", "name": "other", "label": ["Інше"]}
  ],
  "settings": {},
  "translations": [null],
  "translated": ["constraint_message", "label"]
}
```

**Технічні назви (`name`):**
- пиши латиницею, коротко й змістовно: `full_name`, `hh_size`;
- лише літери, цифри, `_`, `-`, `.`;
- назва не може починатися з цифри;
- у межах форми назви не повторюються.

Ці назви стануть назвами колонок у даних і в Google Таблиці, тому міняти їх потім не варто (див. розділ 6).

**Назви варіантів (`name` у `choices`)** теж пиши латиницею, без пробілів. Підписи (`label`) можна писати
будь-якою мовою.

## 2. Типи питань

| Тип | Для чого |
|---|---|
| `text` | текст |
| `integer`, `decimal` | ціле / дробове число |
| `date`, `time`, `datetime` | дата, час |
| `select_one` | один варіант (`select_from_list_name` — список) |
| `select_multiple` | кілька варіантів (у даних через пробіл) |
| `geopoint` | координати |
| `image`, `audio`, `video`, `file` | фото, звук, відео, файл |
| `note` | лише текст для того, хто заповнює |
| `acknowledge` | галочка «так» |
| `calculate` | обчислене значення (`calculation`) |
| `range` | шкала (`parameters`: `start=1 end=10 step=1`) |
| `rank` | впорядкування варіантів |
| `start`, `end`, `today`, `deviceid`, `username` | службові: час початку й кінця, дата, пристрій, хто збирав |

`start` і `end` варто додавати завжди: вони показують, коли саме заповнювали форму.

Корисні колонки:
- `required` (`true`) — обов'язкове питання;
- `hint` — підказка під питанням;
- `appearance` — вигляд: `minimal` (випадний список), `multiline`, `likert`, `field-list` для груп;
- `default` — значення за замовчуванням;
- `choice_filter` — фільтр варіантів.

## 3. Умови, обмеження, обчислення

- **Показати питання за умовою:** `"relevant": "${visits} >= 1"` або `"relevant": "selected(${needs}, 'other')"`.
  Для `select_one`: `"${gender} = 'woman'"`.
- **Обмеження:** `"constraint": ". > 0"` (`.` означає це саме питання) разом з `constraint_message`.
- **Обчислення:** `{"type": "calculate", "name": "big_family", "calculation": "if(${household_size} > 4, 'yes', 'no')"}`.
- **Каскадні списки** (область → район → громада → населений пункт) уже готові в золотому стандарті: у
  `choices` колонка-фільтр, наприклад `"oblast": "lvivska"`, а в питанні `"choice_filter": "oblast=${oblast}"`.

## 4. Групи й повторювані групи

```json
{"type": "begin_group", "name": "contacts", "label": ["Контакти"], "appearance": "field-list"},
{"type": "text", "name": "phone", "label": ["Телефон"]},
{"type": "end_group"},
{"type": "begin_repeat", "name": "members", "label": ["Член родини"], "repeat_count": "${household_size}"},
{"type": "text", "name": "m_name", "label": ["Ім'я"]},
{"type": "integer", "name": "m_age", "label": ["Вік"]},
{"type": "end_repeat"}
```

У даних питання групи має назву `contacts/phone`. Повторювана група дає список записів
`members: [{"members/m_name": …}, …]`. В Excel вона потрапляє на окремий аркуш.

## 5. Кілька мов

```json
"translations": ["Українська (uk)", "English (en)"],
"translated": ["label"],
"survey": [{"type": "text", "name": "q1", "label": ["Ім'я", "Name"]}]
```

Кожен підпис тоді задається списком у тому ж порядку, що й мови. Перша мова використовується за
замовчуванням.

## 6. Зміна наявної форми

1. Збережи копію форми (`api.md`, розділ 9).
2. Знайди місце зміни й зроби її прямо на сторінці Kobo (`api.md`, розділ 4). Безпечно:
   - додавати питання й варіанти;
   - змінювати підписи, підказки, умови та порядок у межах групи.

   Ризиковані зміни питань і варіантів, на які вже є відповіді, — SKILL.md, «Захист», п. 3. Зміну питань
   стандарту звір зі стандартом (SKILL.md, «Золотий стандарт»).
   Замість них додай нове питання, а старе приховай: `"relevant": "false()"`.
3. Якщо треба, розгорни (`api.md`, розділ 5).
4. Якщо зміна вийшла невдалою, поверни попередню версію: Kobo зберігає всі версії форми (`api.md`, розділ 4).
