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

Виконай цей код на будь-якій сторінці `https://eu.kobotoolbox.org`. Входити в акаунт не треба. Код треба
виконати ще раз після перезавантаження сторінки або переходу на іншу.

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

  // Kobo request with the employee's key: {status, data}. status 0 means it was never sent.
  async function kobo(method, path, body) {
    const url = new URL(path, location.origin);
    if (url.origin !== location.origin) return {status: 0, error: 'ключ надсилаємо лише на цей сайт'};
    if (!key) return {status: 0, error: 'спершу kobo.connect(ключ)'};
    const form = body instanceof FormData;
    const r = await fetch(url, {
      method,
      credentials: 'omit', // only the key decides whose account this is
      headers: {
        Authorization: 'Token ' + key,
        Accept: 'application/json',
        ...(body === undefined || form ? {} : {'Content-Type': 'application/json'}),
      },
      body: body === undefined || form ? body : JSON.stringify(body),
    });
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
    const asset = `/api/v2/assets/${uid}/`;
    const a = (await kobo('GET', asset)).data;
    const assignable = new Set((a.assignable_permissions || []).map((p) => last(p.url)));
    const wanted = ROLES[role].filter((p) => !assignable.size || assignable.has(p));
    const before = has(a, user);
    for (const p of wanted.filter((p) => !before.has(p))) {
      // 400 can mean "already implied by another permission": the re-read below decides
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

  // Saves a file from Kobo into the browser's downloads on this computer.
  kobo.download = async (path, filename) => {
    const url = new URL(path, location.origin);
    if (url.origin !== location.origin || !key) return {status: 0};
    const r = await fetch(url, {credentials: 'omit', headers: {Authorization: 'Token ' + key}});
    if (!r.ok) return {status: r.status};
    const link = document.createElement('a');
    link.href = URL.createObjectURL(await r.blob());
    link.download = filename;
    link.click();
    return {status: r.status, saved: filename};
  };

  return kobo;
})();
```

Після цього: `await kobo.connect('<ключ з kobo-ключ.txt>')`. Відповідь буде `{ok: true, username}` або
`{ok: false, why}` (що робити — у розділі «Ключ» у SKILL.md).

Кожен запит повертає `{status, data}`. **Повертай собі лише потрібне:** відбирай поля через `map`, а
великі дані рахуй прямо на сторінці. Тоді розмова не забивається тисячами рядків.

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

**Копія наявної форми:** те саме тіло, але `{clone_from: '<uid>', name: 'Назва', asset_type: 'survey'}`.

**З файлу XLSForm** (Excel у робочій теці):
1. Прочитай файл і перетвори його на base64. Читати файли на комп'ютері можна будь-яким способом.
2. Надішли файл у Kobo:
   ```
   const bytes = Uint8Array.from(atob(B64), (c) => c.charCodeAt(0));
   const f = new FormData();
   f.append('library', 'false');
   f.append('file', new Blob([bytes]), 'form.xlsx');
   const task = (await kobo('POST', '/api/v2/imports/', f)).data;
   for (let i = 0; i < 60; i++) {
     const s = (await kobo('GET', `/api/v2/imports/${task.uid}/`)).data;
     if (s.status === 'complete') return (s.messages.created || s.messages.updated)[0].uid;
     if (s.status === 'error') return {error: s.messages};
     await new Promise((ok) => setTimeout(ok, 2000));
   }
   ```
3. Дай формі назву: `kobo('PATCH', '/api/v2/assets/<uid>/', {name: 'Назва'})`.

**Далі для кожної нової форми:**
1. Поділися з організацією: `await kobo.share(uid, 'kobo_ymbefree')` для «Будь вільний»,
   `'kobo_edobro'` для «Є добро», для обох — обидва виклики. Перевір, що `ok: true`.
2. Якщо форма готова до роботи, розгорни її: `await kobo.deploy(uid)`. Відповідь 200 чи 201 означає успіх.

## 4. Зміна форми і повернення до попередньої версії

1. Збережи копію форми (розділ 9). Візьми `content` з подробиць форми і внеси зміни.
2. Якщо у формі вже є відповіді, з'ясуй, на які питання вони є. Це ключі записів (розділ 7), наприклад
   `household/hh_size`. Якщо зміна прибирає, перейменовує, переносить таке питання чи змінює його тип,
   спершу поговори з працівником (SKILL.md, «Захист», п. 3).
3. Збережи: `kobo('PATCH', '/api/v2/assets/<uid>/', {content})`.
4. Якщо форма розгорнута і зміни мають запрацювати одразу, виконай `kobo.deploy(uid)`.

**Повернути попередню версію.** Kobo зберігає всі версії форми:
1. Список версій: `kobo.all('/api/v2/assets/<uid>/versions/?limit=100')` → `uid`, `date_modified`,
   `date_deployed`.
2. Візьми `content` потрібної версії: `/api/v2/assets/<uid>/versions/<версія>/`.
3. Збережи цей `content`, як у пункті 3 вище, і за потреби розгорни.

Так само можна повернути форму з копії в `Kobo-копії` (розділ 9): узяти з файлу `content` і зберегти його.

## 5. Розгортання, архів, посилання

- **Розгорнути** (нову форму чи нову версію): `kobo.deploy(uid)`.
- **Архівувати** (форма перестає приймати відповіді):
  `kobo('PATCH', '/api/v2/assets/<uid>/deployment/', {active: false})`.
- **Повернути з архіву:** той самий запит з `{active: true}`.
- **Посилання.** Після розгортання в подробицях форми є `deployment__links`:
  - `url` — веб-форма для заповнення в браузері;
  - `offline_url` — та сама форма для роботи без інтернету.

  У KoboCollect збирачі додають сервер `https://kc-eu.kobotoolbox.org` і свій логін, а потім завантажують
  форму («Get Blank Form»). Бачать вони лише форми, якими з ними поділилися.

## 6. Доступ колегам

- **Чи є такий користувач:** `kobo('GET', '/api/v2/users/<логін>/')` → 200.
- **Дати доступ:** `kobo.share(uid, '<логін>', 'view' | 'edit' | 'full')`.
  - `view` — лише бачити форму й відповіді;
  - `edit` — ще й змінювати форму, додавати й виправляти відповіді;
  - `full` — усе, зокрема видаляти.
- **Відкликати** (спершу «Ви впевнені?»; ніколи для `kobo_ymbefree` і `kobo_edobro`):
  ```
  const a = (await kobo('GET', '/api/v2/assets/<uid>/')).data;
  for (const p of a.permissions.filter((p) => p.user.endsWith('/users/<логін>/'))) {
    await kobo('DELETE', p.url);   // 204, або 404, якщо право вже зникло разом з іншим
  }
  ```

## 7. Відповіді: читання, виправлення, статуси, видалення

- **Усі відповіді:** `kobo.all('/api/v2/assets/<uid>/data/?limit=1000')`. Форма, яку ще не розгортали,
  відповідей не має: Kobo відповідає 400.
- **Великі дані:**
  - рахуй підсумки прямо на сторінці й повертай лише цифри;
  - якщо потрібні самі записи, бери частинами: `&start=0&limit=200`, `&start=200…`.

  Як виглядають записи, описано в `data-and-reports.md`.
- **Виправити значення** (питання не з повторюваної групи):
  ```
  kobo('PATCH', '/api/v2/assets/<uid>/data/bulk/',
    {payload: {submission_ids: [12, 15], data: {'household/hh_size': '4', city: 'lviv'}}})
  ```
  - Значення пиши, як у даних: технічну назву варіанта, а не підпис.
  - Питання в групі пиши повним шляхом.
  - Питання з повторюваних груп так не змінити. Їх виправляють у Kobo вручну: Data → запис → Edit.
- **Статус перевірки:**
  ```
  kobo('PATCH', '/api/v2/assets/<uid>/data/validation_statuses/',
    {payload: {submission_ids: [12, 15], 'validation_status.uid': 'validation_status_approved'}})
  ```
  Інші статуси: `validation_status_not_approved`, `validation_status_on_hold`.
- **Видалити відповіді** (лише після «так»): для кожного номера
  `kobo('DELETE', '/api/v2/assets/<uid>/data/<_id>/')` → 204.
- **Видалити форму** (лише після «так»): `kobo('DELETE', '/api/v2/assets/<uid>/')` → 204.

## 8. Excel, фото й файли

**Excel з людськими підписами** (так само, як вивантажує сам Kobo):
```
const e = (await kobo('POST', '/api/v2/assets/<uid>/exports/', {type: 'xls', lang: '_default',
  fields_from_all_versions: true, hierarchy_in_labels: false, group_sep: '/', multiple_select: 'both'})).data;
for (let i = 0; i < 90; i++) {
  const s = (await kobo('GET', `/api/v2/assets/<uid>/exports/${e.uid}/`)).data;
  if (s.status === 'complete') return await kobo.download(s.result, 'Назва форми.xlsx');
  if (s.status === 'error') return {error: s.messages};
  await new Promise((ok) => setTimeout(ok, 2000));
}
```
Файл з'явиться в теці «Завантаження» на комп'ютері; скажи про це працівнику. Якщо завантажити не вдалося,
збери Excel сам: візьми записи (розділ 7), підписи питань з опису форми, і поклади файл у робочу теку.

**Фото й файли** відповіді лежать у записі в `_attachments`. Щоб зберегти файл на комп'ютер:
`kobo.download(att.download_url, att.filename.split('/').pop())`. Фото бувають великі, тому спершу скажи,
скільки їх, і завантажуй лише потрібні.

## 9. Копія перед зміною

Копії лежать у робочій теці працівника: `Kobo-копії/<назва форми>/`. Кожна копія — це файл з датою й часом
у назві, наприклад `2026-11-05 14-30 форма.json`. Записуй файли так само, як записуєш будь-який файл у
робочу теку. Після запису перевір, що файл з'явився.

**Форма:**
```
const a = (await kobo('GET', '/api/v2/assets/<uid>/')).data;
return {uid: a.uid, name: a.name, saved: new Date().toISOString(),
  deployed_version_id: a.deployed_version_id, content: a.content};
```
Збережи це як `… форма.json`.

**Відповіді.** Візьми записи, які зміняться чи зникнуть (розділ 7, з фільтром за `_id`). Для видалення
форми — усі записи. Збережи їх як `… відповіді.json`. Якщо записів тисячі, бери їх частинами по 500 і
дописуй у кілька файлів: `… відповіді 1.json`, `… відповіді 2.json`.

Фото в копію не входять.

**Повернути з копії:**
- форму — розділ 4;
- відповіді — значення окремих полів можна повернути виправленням (розділ 7).

Видалені відповіді назад у Kobo повертає адміністратор.
