# Перевірки перед злиттям у dev

Для PR [№2](https://github.com/Shkirmantsev/ProjectExpert/pull/2) у правилах
`FirstBaseRuleset` потрібні результат CodeQL і щонайменше одне схвалення.
Автоматичний Copilot review вже ввімкнений, з повторною перевіркою після push.
Також увімкнене окреме правило GitHub Code Quality з порогом `notes`.
Це налаштування перевірено 4 жовтня 2026 року; воно може змінитися.

Workflow [.github/workflows/codeql.yml](.github/workflows/codeql.yml) перевіряє
Python і завантажує результати в Code Scanning. Він запускається для PR у `dev`
та `main`, після push у ці гілки й вручну. Навіть PR лише з документацією
отримує перевірку. Workflow не надає схвалення від імені людини.

## 1. Опублікувати коміт

Після створення локального коміту виконайте:

```bash
git push origin feature/generate-init-project
```

Відкрийте PR №2 → **Checks**. Має з'явитися **CodeQL / Analyze Python**.
Дочекайтеся завершення. Якщо перевірка червона, відкрийте її → **Details**,
щоб побачити причину.

## 2. Перевірити налаштування CodeQL

Відкрийте [Settings → Advanced Security](https://github.com/Shkirmantsev/ProjectExpert/settings/security_analysis).
У рядку **CodeQL analysis** перевірте тип налаштування.

- Якщо активний **Default setup**, відкрийте меню цього рядка →
  **Switch to advanced** → підтвердьте **Disable CodeQL**. Це вимикає default
  setup, щоб результати завантажував наш workflow. Не створюйте другий
  CodeQL workflow через шаблон GitHub.
- Якщо CodeQL ще не налаштований, наш файл є конфігурацією advanced setup.
  Після push перевірте його запуск у **Actions**.
- Якщо Actions заборонені, відкрийте **Settings → Actions → General** і
  дозвольте GitHub Actions, включно з `actions/checkout` та
  `github/codeql-action`. Збережіть налаштування.

Див. [офіційну інструкцію GitHub](https://docs.github.com/en/code-security/how-tos/find-and-fix-code-vulnerabilities/configure-code-scanning/configuring-advanced-setup-for-code-scanning).

## 3. Якщо GitHub досі очікує результат для dev

У `dev` ще немає цього workflow. Якщо PR перевірений, але GitHub досі пише
**Waiting for Code Scanning results**, спочатку потрібен базовий аналіз `dev`.
GitHub порівнює результати PR із результатами цільової гілки.

1. Відкрийте **Code** → у списку гілок виберіть **dev**.
2. Натисніть **Add file → Create new file**.
3. У полі назви введіть `.github/workflows/codeql.yml`.
4. Скопіюйте повний вміст цього файлу з `feature/generate-init-project`.
5. Натисніть **Commit changes…**. Якщо ваші права обходу правил дозволяють,
   оберіть коміт безпосередньо в `dev`. Якщо GitHub вимагає PR, створіть
   окрему гілку й PR у `dev` лише з цим файлом. Його початкове злиття має
   виконати користувач із дозволом обходу правил; схвалення саме по собі
   не усуває відсутність базового сканування.
6. Відкрийте **Actions → CodeQL** і дочекайтеся успішного запуску для `dev`.
7. У **Actions** відкрийте запуск CodeQL для PR №2 →
   **Re-run all jobs**. Перевірте блок злиття в PR ще раз.

Не вимикайте весь ruleset для цього. Якщо ніхто не має права обходу,
адміністратор має погодити спосіб початкового встановлення workflow.
Для ручного запуску через **Run workflow** файл має бути також у `main`,
оскільки це default branch. Для автоматичного push-аналізу `dev`
достатньо файлу в `dev`.

Див. [як GitHub запускає та порівнює сканування](https://docs.github.com/en/code-security/reference/code-scanning/workflow-configuration-options).

## 4. Отримати схвалення PR

У PR №2 відкрийте **Conversation**. Праворуч у **Reviewers** натисніть
шестерню та виберіть іншого учасника з правом запису. Якщо людей у списку
немає, відкрийте **Settings → Collaborators → Add people**, додайте
потрібного користувача й дочекайтеся прийняття запрошення.

Рев'юер відкриває PR → **Files changed → Review changes → Approve →
Submit review**. Якщо для змінених файлів визначені CODEOWNERS, потрібне
схвалення відповідного власника коду, бо це також вимагає поточний ruleset.
Автор не може схвалити власний PR.

Див. [правила схвалення GitHub](https://docs.github.com/en/pull-requests/how-tos/review-pull-requests/approving-a-pull-request-with-required-reviews).

Якщо ви працюєте самі й хочете дозволити PR без іншого рев'юера, це окреме
рішення про правила проєкту: **Settings → Rules → Rulesets →
FirstBaseRuleset → Require a pull request before merging**. Змініть
**Required approvals** на `0` і вимкніть **Require review from Code Owners**,
якщо не плануєте такого схвалення. Натисніть **Save changes**.
Це послабить вимогу схвалення для **main і dev**, бо ruleset охоплює обидві
гілки. Workflow цього налаштування не змінює.

Якщо ви хочете саме схвалення від Copilot, а не лише коментарі, відкрийте
**Settings → Copilot → Code review → Auto-approval**. Якщо ці опції доступні,
увімкніть **Allow Copilot to approve pull requests** і
**Allow Copilot approvals to count toward merge requirements**.
Перевірте обмеження **File paths**: схвалення зараховується лише для PR,
які підпадають під них. Це функція public preview; автоматичний запит review
не гарантує схвалення й не скасовує інші вимоги ruleset.
Для ручного запиту у PR відкрийте **Reviewers** і виберіть **Copilot**;
для повторного review скористайтеся кнопкою повторного запиту біля нього.
Див. [налаштування Copilot review та схвалень](https://docs.github.com/en/copilot/how-tos/copilot-on-github/set-up-copilot/configure-code-review).

## 5. Якщо з'явиться блокування Code Quality

CodeQL і GitHub Code Quality — окремі перевірки. Відкрийте
**Settings → Code quality** у розділі **Security / Security and quality**.
Якщо сервіс не налаштований, натисніть **Enable code quality**,
перевірте вибрані мови й runner та натисніть **Save changes**.
Якщо сервіс недоступний для вашого облікового запису,
адміністратору потрібно переглянути вимогу **Require code quality results**
у **Settings → Rules → Rulesets → FirstBaseRuleset**.
Не змінюйте поріг лише для приховування знайдених проблем.

Див. [увімкнення Code Quality](https://docs.github.com/en/code-security/how-tos/maintain-quality-code/enable-code-quality)
та [опис окремих правил перевірок](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-rulesets/available-rules-for-rulesets).
