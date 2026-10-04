# نظام إدارة الأسطول — BrilliantTech

نظام مستقل عن نظام الموارد البشرية. التصميم الكامل في «مواصفات التنفيذ 1.1».
هذه هي **المرحلة M0 (الأساس)**.

## ما تم في M0

| الجزء | المحتوى |
|---|---|
| الهوية | دخول بكلمة مرور (argon2id)، قفل بعد 5 محاولات، تحقق بخطوتين (TOTP) مع منع إعادة استخدام الرمز، جلسات على الخادم (Cookie httpOnly) مع CSRF، انتهاء الجلسة بالخمول وبالمدة، لغة لكل مستخدم |
| الصلاحيات | كتالوج كامل للنظام كله من الآن (`app/core/permissions.py`): 32 وحدة و 88 صلاحية على مستوى الوحدة والإجراء، مع تمييز الصلاحيات الحساسة. أدوار من الإعدادات دون برمجة، وأدوار جاهزة من الـ BRD، ولا يستطيع أحد منح أكثر مما يملك |
| الشركات | الكيان القانوني: عليها الموظفون (على ورق الشركة) والسيارات (ملك الشركة). السجل التجاري والترخيص وتاريخ انتهائه وملف القوى العاملة. نطاق الرؤية بالشركة: كل الشركات افتراضياً، أو شركات محددة |
| الفروع | مواقع تشغيلية فقط، فرع رئيسي جاهز، ولا تقيّد رؤية أحد |
| اللغات | العربية والإنجليزية مع الكود (`app/modules/i18n/catalog`)، وتعديل أي نص أو إضافة لغة كاملة (مثل الأردو للسائقين) من الشاشة دون نشر، مع لغة رجوع لما لم يُترجم بعد، وحماية المتغيرات مثل `{name}`. الأسماء (الشركات والأدوار والفروع) تُحفظ بكل اللغات |
| الإعدادات | 8 أقسام مكتوبة الأنواع، وإعدادات العميل في `deploy/tenants/<client>/settings.json` |
| التدقيق | كل عملية حساسة، إضافة فقط (trigger)، وعرض مفلتر بنطاق الشركات |
| الأحداث | Outbox في نفس الـ transaction، وناشر بـ SKIP LOCKED، ومستهلكون idempotent |
| القاعدة | ترحيلات SQL صريحة، ومستخدم تطبيق بأقل الصلاحيات و `statement_timeout` |
| التشغيل | Dockerfiles، و compose كامل (Postgres + pgBackRest، ونسختا Redis، و Celery)، و CI |

**الاختبارات:** 43 اختباراً على PostgreSQL 16 حقيقي، منها:
- كل صلاحية ووحدة ورسالة خطأ وإعداد له نص بالعربية والإنجليزية، والأدوار الجاهزة لا تستخدم إلا صلاحيات موجودة.
- عزل الشركات، ومنع تصعيد الصلاحيات، وصلاحيات مستخدم التطبيق في القاعدة.
- الـ models مطابقة للترحيلات.

### إضافة صلاحية أو نص جديد

1. الصلاحية في `app/core/permissions.py`، ثم استخدامها بـ `require_permission("module.action")`.
2. اسمها في `catalog/ar.json` و `catalog/en.json` (namespace `permissions`)، وكذلك رسائل الأخطاء الجديدة (`errors`).
3. اختبار `test_catalog.py` يفشل إذا نسيت أي خطوة.

## التشغيل محلياً

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt

# الاختبارات: أي PostgreSQL 16 يسمح بإنشاء قواعد بيانات
export TEST_ADMIN_DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/postgres
pytest
ruff check . && ruff format --check .

# تشغيل الخادم
export DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/fleet SECRET_KEY=change-me COOKIE_SECURE=false
alembic upgrade head
ADMIN_PASSWORD='...' python -m app.ops.bootstrap --username admin --full-name "System Administrator"
python -m app.ops.apply_settings ../deploy/tenants/ajwad/settings.json
uvicorn app.main:create_app --factory --reload      # التوثيق: http://localhost:8000/api/docs
```

## النشر (Coolify)

1. مورد Docker Compose من `deploy/docker-compose.yml`، والدومين على خدمة `web` فقط.
2. الأسرار من `deploy/.env.example` في شاشة متغيرات البيئة.
3. بعد أول تشغيل: `bootstrap` ثم `apply_settings` (أعلاه) داخل حاوية `api`، ثم أوامر النسخ في `deploy/backup-and-restore.sh`.
4. مستخدم التطبيق `fleet_app` يُنشأ مرة واحدة بكلمة مرور، وكل ترحيل يمنحه صلاحياته تلقائياً.

## ما لم يُختبر بعد

- بناء صور Docker وتشغيل compose و CI (لا يوجد Docker في بيئة الإعداد): أول خطوة عند الفريق.
- أوامر النسخ والاستعادة على الخوادم الحقيقية (شروط القسم 15.4 في المواصفات).
- الواجهة في `web/public` ما زالت قالب الواجهات ببيانات تجريبية، وربطها بالـ API يبدأ في M1.

## التالي: M1

الموظفون والسائقون، والسيارات، والعهدة (قيود عدم التداخل)، والعداد، وربط جهاز السائق بـ OTP، واستقبال نقاط التتبع (الكود المختبر في المواصفات)، والخريطة الحية، وتنبيه الانقطاع، وربط شاشات الدخول والمستخدمين والإعدادات في الواجهة.
