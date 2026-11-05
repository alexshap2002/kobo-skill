# Запити до Kobo зі сторінки eu.kobotoolbox.org

## Зміст
1. Помічник
2. Форми: список і подробиці
3. Створення форми
4. Зміна форми і повернення до попередньої версії
5. Розгортання, архів, посилання
6. Доступ колегам
7. Відповіді: читання, виправлення, статуси, видалення
8. Excel, фото й файли
9. Копія перед зміною

## 1. Помічник

- Відкрий у браузері `https://eu.kobotoolbox.org/`. Входити в акаунт не треба.
- Виконай помічник нижче **дослівно**, нічого не скорочуючи й не переписуючи. У ньому закладено правила
  безпеки: ключ іде лише на eu.kobotoolbox.org, ключі головних акаунтів не приймаються.
- Потім виконай `await kobo.connect('<ключ>')`. Ключ з `kobo-ключ.txt` вписуй прямо в цей виклик:
  працівник дав його саме для роботи з його Kobo. У відповідях працівнику ключ не повторюй.
- Кожен фрагмент коду з цього файлу запускай як `(async () => { … })()`. Тоді працюють і `await`, і
  `return`.
- Один запуск має тривати не довше 20 секунд. Довгі справи (вивантаження, імпорт) роби кількома запусками:
  перший створює завдання, наступні лише перевіряють його через `kobo.wait` (розділи 3 і 8).
- Якщо після запуску `typeof kobo` дорівнює `'undefined'`, сторінка не дала виконати код. Тоді відкрий
  `https://eu.kobotoolbox.org/static/favicon.png` і виконай помічник там. Це той самий сайт, усе інше
  працює так само.
- Після перезавантаження сторінки чи переходу на іншу помічник зникає. Виконай його і `kobo.connect` знову.

```js
window.kobo = (() => {
  const MAIN = ['kobo_ymbefree', 'kobo_edobro'];
  const ROLES = {
    view: ['view_asset', 'view_submissions'],
    edit: ['view_asset', 'change_asset', 'view_submissions', 'add_submissions', 'change_submissions',
      'validate_submissions'],
    full: ['view_asset', 'change_asset', 'manage_asset', 'view_submissions', 'add_submissions',
      'change_submissions', 'delete_submissions', 'validate_submissions'],
  };
  let key = null;
  let me = null;
  const last = (url) => url.replace(/\/$/, '').split('/').pop();
  const has = (asset, user) => new Set((asset.permissions || [])
    .filter((p) => last(p.user) === user).map((p) => last(p.permission)));

  // Kobo request with the employee's key: {status, data}. status 0 means Kobo never answered.
  async function kobo(method, path, body) {
    const url = new URL(path, location.origin);
    if (url.origin !== location.origin) return {status: 0, error: 'ключ надсилаємо лише на цей сайт'};
    if (!key) return {status: 0, error: 'спершу kobo.connect(ключ)'};
    const form = body instanceof FormData;
    let r;
    try {
      r = await fetch(url, {
        method,
        credentials: 'omit', // only the key decides whose account this is
        headers: {
          Authorization: 'Token ' + key,
          Accept: 'application/json',
          ...(body === undefined || form ? {} : {'Content-Type': 'application/json'}),
        },
        body: body === undefined || form ? body : JSON.stringify(body),
      });
    } catch (e) {
      // a change may still have reached Kobo: check before repeating it
      return {status: 0, error: 'немає зв\'язку з Kobo', maybeSent: method !== 'GET'};
    }
    const text = await r.text();
    let data = text;
    try { data = JSON.parse(text); } catch (e) { /* not JSON: keep the text */ }
    return {status: r.status, data};
  }

  kobo.connect = async (k) => {
    key = String(k).trim();
    const who = await kobo('GET', '/me/');
    if (who.status === 200 && !MAIN.includes(who.data.username)) {
      me = who.data.username;
      return {ok: true, username: me};
    }
    key = null;
    if (who.status === 200) return {ok: false, why: 'головний акаунт організації'};
    if (who.status === 401 || who.status === 403) return {ok: false, why: 'ключ не підійшов', status: who.status};
    return {ok: false, why: 'Kobo не відповідає', status: who.status};
  };

  kobo.all = async (path) => {
    const out = [];
    for (let next = path; next;) {
      const r = await kobo('GET', next);
      if (r.status !== 200) return r;
      out.push(...r.data.results);
      next = r.data.next;
    }
    return {status: 200, data: out};
  };

  // Gives `user` every permission of `role` the form lacks, one at a time, never touching anyone else.
  kobo.share = async (uid, user, role = 'full') => {
    if (!ROLES[role]) return {ok: false, error: 'роль: view, edit або full'};
    const asset = `/api/v2/assets/${uid}/`;
    const got = await kobo('GET', asset);
    if (got.status !== 200) return {ok: false, status: got.status, error: got.data};
    const a = got.data;
    const assignable = new Set((a.assignable_permissions || []).map((p) => last(p.url)));
    const wanted = ROLES[role].filter((p) => !assignable.size || assignable.has(p));
    const before = has(a, user);
    for (const p of wanted.filter((p) => !before.has(p))) {
      // Kobo answers a permission it already has with the existing one; the re-read below decides
      await kobo('POST', `${asset}permission-assignments/`, {
        user: `${location.origin}/api/v2/users/${user}/`,
        permission: `${location.origin}/api/v2/permissions/${p}/`,
      });
    }
    const after = has((await kobo('GET', asset)).data, user);
    const missing = wanted.filter((p) => !after.has(p));
    return {ok: missing.length === 0, missing};
  };

  // The employee's own forms that no organisation fully has, or that one has only partly.
  kobo.unshared = async () => {
    const forms = await kobo.all('/api/v2/assets/?q=asset_type:survey&limit=300');
    if (forms.status !== 200) return forms;
    const out = [];
    for (let a of forms.data.filter((f) => f.owner__username === me)) {
      if (!a.permissions) a = (await kobo('GET', `/api/v2/assets/${a.uid}/`)).data;
      const state = MAIN.map((user) => {
        const got = has(a, user);
        return ROLES.full.every((p) => got.has(p)) ? 'full' : got.size ? 'partial' : 'none';
      });
      if (!state.includes('full') || state.includes('partial')) {
        out.push({uid: a.uid, name: a.name, kobo_ymbefree: state[0], kobo_edobro: state[1]});
      }
    }
    return {status: 200, data: out};
  };

  // Deploys the current version: the first time POST, afterwards PATCH with that version.
  kobo.deploy = async (uid) => {
    const a = (await kobo('GET', `/api/v2/assets/${uid}/`)).data;
    return a.has_deployment
      ? kobo('PATCH', `/api/v2/assets/${uid}/deployment/`, {active: true, version_id: a.version_id})
      : kobo('POST', `/api/v2/assets/${uid}/deployment/`, {active: true});
  };

  // Checks an export or import task for up to `seconds`; run again while its status is not final.
  kobo.wait = async (path, seconds = 20) => {
    const until = Date.now() + seconds * 1000;
    for (;;) {
      const r = await kobo('GET', path);
      if (r.status !== 200 || ['complete', 'error'].includes(r.data.status) || Date.now() > until) return r;
      await new Promise((ok) => setTimeout(ok, 2000));
    }
  };

  // Starts saving a file from Kobo into the browser's downloads. Only started: the browser may ask or block.
  kobo.download = async (path, filename) => {
    const url = new URL(path, location.origin);
    if (url.origin !== location.origin || !key) return {status: 0};
    let r;
    try {
      r = await fetch(url, {credentials: 'omit', headers: {Authorization: 'Token ' + key}});
    } catch (e) {
      return {status: 0, error: 'немає зв\'язку з Kobo'};
    }
    if (!r.ok) return {status: r.status};
    const blob = await r.blob();
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
    return {status: r.status, started: filename, bytes: blob.size};
  };

  return kobo;
})();
```

Що повертають виклики:
- **`kobo(метод, шлях, тіло)`** → `{status, data}`. `status: 0` означає, що Kobo не відповів. Якщо при
  цьому `maybeSent: true`, зміна могла дійти: перевір, перш ніж повторювати.
- **`kobo.connect(ключ)`** → `{ok: true, username}` або `{ok: false, why}`. `why` буває: «ключ не
  підійшов», «головний акаунт організації», «Kobo не відповідає».
- **`kobo.all(шлях)`** → усі сторінки списку разом.
- **`kobo.share(uid, логін, роль)`** → `{ok, missing}`.
- **`kobo.unshared()`** → власні форми працівника, яких організація не має повністю.
- **`kobo.deploy(uid)`** → розгортає форму.
- **`kobo.wait(шлях)`** → стан вивантаження чи імпорту.
- **`kobo.download(шлях, назва)`** → `{started, bytes}`. Завантаження лише запущено (розділ 8).

**Повертай собі лише потрібне.** Відбирай поля через `map`, а великі дані рахуй прямо на сторінці. Тоді
розмова не забивається тисячами рядків, і нічого не обрізається.

## 2. Форми: список і подробиці

```
const r = await kobo.all('/api/v2/assets/?q=asset_type:survey&limit=300');
return r.data.map((a) => ({uid: a.uid, name: a.name, owner: a.owner__username,
  status: a.deployment_status, answers: a.deployment__submission_count}));
```

- `status`: `deployed` — розгорнута, `draft` — чернетка, `archived` — архівна.
- Форми з іншим `owner` — чужі, ними з працівником поділилися.
- Працівник називає форму назвою; знайди її `uid` у цьому списку. Якщо збігів кілька, перепитай.

Подробиці: `kobo('GET', '/api/v2/assets/<uid>/')`. Найпотрібніше там:
- `content` — опис форми (чернетка, яку редагують);
- `has_deployment`, `version_id`, `deployed_version_id`;
- `permissions` — хто має доступ: `user` і `permission` закінчуються логіном і назвою права;
- `deployment__links` — посилання для заповнення.

Що люди заповнюють зараз (розгорнута версія): `/api/v2/assets/<uid>/versions/<deployed_version_id>/` →
`content`.

**Поширення на організацію.** Форма поділена, коли в `permissions` є `kobo_ymbefree` або `kobo_edobro` з
усіма правами `full`.
- Усі власні форми працівника, де цього бракує: `await kobo.unshared()`. Повертає `uid`, `name` і стан для
  кожної організації: `full`, `partial` або `none`.
- Поділитися або доповнити права: `kobo.share(uid, 'kobo_ymbefree')` чи `kobo.share(uid, 'kobo_edobro')`.

## 3. Створення форми

Спершу запитай, для якої організації форма (SKILL.md, «Кожна форма — в організації»).

**З опису** (формат — у `forms.md`):
```
const r = await kobo('POST', '/api/v2/assets/', {name: 'Назва', asset_type: 'survey', content});
return {status: r.status, uid: r.data.uid};   // 201 — створено
```
Під час створення Kobo опис не перевіряє. Помилки в описі він назве при розгортанні: відповідь 400 з
поясненням. Тоді виправ опис і розгорни ще раз.

**Копія наявної форми:** те саме тіло, але `{clone_from: '<uid>', name: 'Назва', asset_type: 'survey'}`.

**З файлу XLSForm** (Excel у робочій теці):
1. Прочитай файл і перетвори його на base64. Читати файли з робочої теки можна будь-яким способом.
2. Перший запуск надсилає файл:
   ```
   const bytes = Uint8Array.from(atob(B64), (c) => c.charCodeAt(0));
   const f = new FormData();
   f.append('library', 'false');
   f.append('name', 'Назва форми');
   f.append('file', new Blob([bytes]), 'form.xlsx');
   const t = await kobo('POST', '/api/v2/imports/', f);
   return {status: t.status, task: t.data.uid};   // 201 — файл прийнято
   ```
3. Наступні запуски лише перевіряють, доки стан не стане `complete` чи `error`:
   ```
   const s = await kobo.wait('/api/v2/imports/<task>/');
   if (s.data.status === 'complete') return {uid: (s.data.messages.created || s.data.messages.updated)[0].uid};
   return {status: s.status, state: s.data.status, messages: s.data.messages};
   ```
   Якщо перевірка обірвалася, файл удруге не надсилай: перевір те саме завдання ще раз.

**Далі для кожної нової форми:**
1. Поділися з організацією: `await kobo.share(uid, 'kobo_ymbefree')` для «Будь вільний»,
   `'kobo_edobro'` для «Є добро», для обох — обидва виклики. Перевір, що `ok: true`.
2. Якщо форма готова до роботи, розгорни її: `await kobo.deploy(uid)`. Відповідь 200 чи 201 означає успіх.

## 4. Зміна форми і повернення до попередньої версії

1. Збережи копію форми (розділ 9).
2. Знайди місце зміни. Повертай собі лише короткий перелік питань, а не весь опис:
   ```
   const c = (await kobo('GET', '/api/v2/assets/<uid>/')).data.content;
   return c.survey.map((q, i) => [i, q.type, q.name, (q.label || [])[0]]);
   ```
3. Якщо у формі вже є відповіді (`deployment__submission_count` більше 0), вважай, що відповіді є на всі
   наявні питання й варіанти. Ризиковану зміну спершу обговори з працівником (SKILL.md, «Захист», п. 3).
4. Зміну роби на сторінці одним фрагментом. Опис форми в розмову не переписуй: так ненароком не зіпсуєш
   інші питання.
   ```
   const path = '/api/v2/assets/<uid>/';
   const c = (await kobo('GET', path)).data.content;
   c.survey.splice(5, 0, {type: 'integer', name: 'children_n', label: ['Скільки дітей?']});   // приклад
   return (await kobo('PATCH', path, {content: c})).status;   // 200 — збережено
   ```
   Колонки, задані списками, мають бути в `translated` (`forms.md`, розділ 1).
5. Якщо форма розгорнута і зміни мають запрацювати одразу, виконай `kobo.deploy(uid)`.

**Повернути попередню версію.** Kobo зберігає всі версії форми:
1. Список версій: `kobo.all('/api/v2/assets/<uid>/versions/?limit=100')` → `uid`, `date_modified`,
   `date_deployed`.
2. Поверни вибрану версію прямо на сторінці:
   ```
   const v = (await kobo('GET', '/api/v2/assets/<uid>/versions/<версія>/')).data.content;
   return (await kobo('PATCH', '/api/v2/assets/<uid>/', {content: v})).status;
   ```
3. За потреби розгорни.

Версії Kobo — головний шлях повернення. Копія в `Kobo-копії` — запасний, коли потрібної версії в Kobo
немає. Тоді візьми `content` з файлу копії й збережи його так само.

## 5. Розгортання, архів, посилання

- **Розгорнути** (нову форму чи нову версію): `kobo.deploy(uid)`. Відповідь 400 означає помилку в описі
  форми: Kobo пояснить, що не так.
- **Архівувати** (форма перестає приймати відповіді):
  `kobo('PATCH', '/api/v2/assets/<uid>/deployment/', {active: false})`.
- **Повернути з архіву:** той самий запит з `{active: true}`.
- **Посилання.** Після розгортання в подробицях форми є `deployment__links`:
  - `url` — веб-форма для заповнення в браузері;
  - `offline_url` — та сама форма для роботи без інтернету.

  У KoboCollect збирачі додають сервер `https://kc-eu.kobotoolbox.org` і свій логін, а потім завантажують
  форму («Get Blank Form»). Бачать вони лише форми, якими з ними поділилися.

## 6. Доступ колегам

Потрібні логін колеги в Kobo і назва форми. Якщо їх немає, запитай: «Який у Петра логін у Kobo і до якої
форми дати доступ?»

- **Чи є такий користувач:** `kobo('GET', '/api/v2/users/<логін>/')` → 200.
- **Дати доступ:** `kobo.share(uid, '<логін>', 'view' | 'edit' | 'full')`.
  - `view` — лише бачити форму й відповіді;
  - `edit` — ще й змінювати форму, додавати й виправляти відповіді;
  - `full` — усе, зокрема видаляти.
- **Де в колеги є доступ:** переглянь `permissions` у подробицях власних форм працівника й назви ті, де є
  цей логін.
- **Відкликати.** Ніколи не відкликай доступ у `kobo_ymbefree` і `kobo_edobro`.
  1. Спершу запитай: «Петро (<логін>) більше не бачитиме форму "<назва>" і її відповіді. Забрати доступ?
     Ви впевнені?»
  2. Після «так» виконай:
     ```
     const a = (await kobo('GET', '/api/v2/assets/<uid>/')).data;
     for (const p of a.permissions.filter((p) => p.user.endsWith('/users/<логін>/'))) {
       await kobo('DELETE', p.url);   // 204, або 404, якщо право вже зникло разом з іншим
     }
     ```

## 7. Відповіді: читання, виправлення, статуси, видалення

- **Усі відповіді в порядку подання:**
  `kobo.all('/api/v2/assets/<uid>/data/?limit=1000&sort=' + encodeURIComponent('{"_id":1}'))`. Форма,
  яку ще не розгортали, відповідей не має: Kobo відповідає 400.
- **Великі дані:**
  - рахуй підсумки прямо на сторінці й повертай лише цифри;
  - якщо потрібні самі записи, бери частинами: `&start=0&limit=100`, `&start=100…`.

  Як виглядають записи, описано в `data-and-reports.md`.
- **Про які записи каже працівник.** `_id` — це внутрішній номер Kobo, довге число. «Запис 12» у словах
  працівника — найчастіше 12-й рядок таблиці чи Excel у порядку подання, а не `_id`. Знайди записи за
  порядком або за змістом (ім'я, дата) і покажи їх працівнику, перш ніж щось змінювати.
- **Записи за `_id`:**
  `'/api/v2/assets/<uid>/data/?query=' + encodeURIComponent(JSON.stringify({_id: {$in: [412345678]}}))`.
- **Чужа форма.** Перед зміною перевір у `permissions`, що працівник має право: `change_submissions` для
  виправлень і статусів, `delete_submissions` для видалення. Якщо права немає, копію не роби й скажи:
  «Цю форму з вами поділили лише для перегляду, тому змінити запис не вийде. Попросіть власника форми
  (<логін>) дати вам право на редагування.»
- **Виправити значення** (питання не з повторюваної групи):
  ```
  const r = await kobo('PATCH', '/api/v2/assets/<uid>/data/bulk/',
    {payload: {submission_ids: [412345678], data: {'household/hh_size': '4', city: 'lviv'}}});
  return {status: r.status, failures: r.data.failures};   // 200 і 0 — усе виправлено
  ```
  - Значення пиши, як у даних: технічну назву варіанта, а не підпис.
  - Питання в групі пиши повним шляхом.
  - Питання з повторюваних груп так не змінити. Їх виправляють у Kobo вручну: Data → запис → Edit.
- **Статус перевірки:**
  ```
  kobo('PATCH', '/api/v2/assets/<uid>/data/validation_statuses/',
    {payload: {submission_ids: [412345678], 'validation_status.uid': 'validation_status_approved'}})
  ```
  Інші статуси: `validation_status_not_approved`, `validation_status_on_hold`.
- **Видалити відповіді** (лише після «так»): для кожного `_id`
  `kobo('DELETE', '/api/v2/assets/<uid>/data/<_id>/')` → 204.
- **Видалити форму** (лише після «так»): `kobo('DELETE', '/api/v2/assets/<uid>/')` → 204.

## 8. Excel, фото й файли

**Excel з людськими підписами** (так само, як вивантажує сам Kobo):
1. Перший запуск створює вивантаження:
   ```
   const c = await kobo('POST', '/api/v2/assets/<uid>/exports/', {type: 'xls', lang: '_default',
     fields_from_all_versions: true, hierarchy_in_labels: false, group_sep: '/', multiple_select: 'both'});
   return {status: c.status, export: c.data.uid, error: c.status > 201 ? c.data : undefined};
   ```
   201 означає, що вивантаження створено. 200 — таке саме вже готується, бери його `uid`. 400 буває, якщо
   форму ще не розгортали.
2. Наступні запуски перевіряють і, коли готово, завантажують:
   ```
   const s = await kobo.wait('/api/v2/assets/<uid>/exports/<export>/');
   if (s.data.status === 'complete') return await kobo.download(s.data.result, 'Назва форми.xlsx');
   return {status: s.status, state: s.data.status};   // ще не готово — запусти знову
   ```
3. `started` означає лише, що завантаження почалося. Скажи працівнику: «Файл "Назва форми.xlsx" має
   з'явитися в теці «Завантаження». Якщо браузер спитає про завантаження, натисніть "Дозволити".»
4. Якщо працівник каже, що файлу немає:
   - до 200 записів — збери Excel сам з записів (розділ 7) і поклади в робочу теку;
   - більше — попроси завантажити його в самому Kobo: форма → **Data** → **Downloads**. Вивантаження, яке
     ти вже створив, буде там у списку.

**Фото й файли** відповіді лежать у записі в `_attachments`:
- пропускай ті, де `is_deleted: true`;
- щоб зберегти файл: `kobo.download(att.download_url, att.media_file_basename)`.

Фото бувають великі, тому спершу скажи, скільки їх, і завантажуй лише потрібні. Перед кількома файлами
скажи: «Якщо браузер спитає про завантаження кількох файлів, натисніть "Дозволити"». Потім спитай, чи файли
з'явилися.

## 9. Копія перед зміною

**Де.** Копії лежать у робочій теці працівника: `Kobo-копії/<назва форми>/`. У назві теки заміни символи
`/ \ : * ? " < > |` на `-`. Кожна копія — це файл з датою й часом у назві, наприклад
`2026-11-05 14-30 форма.json`.

**Як.** Записуй файли так само, як будь-який файл у робочу теку. Після запису перевір, що файл є і що в
ньому все, що ти збирався зберегти: стільки питань чи записів, скільки в Kobo. Якщо чогось бракує (результат
зі сторінки прийшов обрізаним), бери менші частини. Поки копія неповна, зміну не роби.

**Форма** — перед будь-якою її зміною:
```
const a = (await kobo('GET', '/api/v2/assets/<uid>/')).data;
return {uid: a.uid, name: a.name, saved: new Date().toISOString(),
  deployed_version_id: a.deployed_version_id, content: a.content};
```
Збережи це як `… форма.json`.

**Відповіді:**
- **Перед виправленням значень чи статусів** зберігай лише `_id` і старі значення того, що зміниться,
  наприклад `[{"_id": 412345678, "city": "kyiv"}]`. Файл — `… старі значення.json`. Цього досить, щоб
  повернути.
- **Перед видаленням окремих записів** зберігай їх повністю: запит за `_id` (розділ 7), частинами по 100.
  Файл — `… відповіді.json`.
- **Перед видаленням форми:**
  - до 200 відповідей — так само, як окремі записи;
  - більше — копією буде Excel, який вивантажує сам Kobo (розділ 8): він точний і не проходить через
    розмову. Файл ляже в «Завантаження». Видаляй форму лише після того, як працівник підтвердить, що файл
    там є.

Фото в копію не входять.

**Повернути з копії:**
- форму — розділ 4;
- значення — виправленням зі `… старі значення.json` (розділ 7).

Видалені відповіді назад у Kobo повертає адміністратор.
