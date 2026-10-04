# نظام إدارة الأسطول — BrilliantTech

نظام مستقل عن نظام الموارد البشرية. التصميم الكامل في «مواصفات التنفيذ 1.1».
هذه هي **المرحلة M0 (الأساس)**.

## ما تم في M0

| الجزء | المحتوى |
|---|---|
| الهوية | دخول بكلمة مرور (argon2id)، قفل بعد 5 محاولات، تحقق بخطوتين (TOTP) مع منع إعادة استخدام الرمز، جلسات على الخادم (Cookie httpOnly) مع CSRF، انتهاء الجلسة بالخمول وبالمدة، تغيير وإعادة تعيين كلمة المرور |
| الصلاحيات | أدوار من الإعدادات دون برمجة، صلاحية + نطاق فروع، ولا يستطيع أحد منح أكثر مما يملك |
| الشركات والفروع | إنشاء وتعديل بإصدارات (optimistic locking)، والفرع خارج النطاق يظهر كأنه غير موجود |
| الإعدادات | 8 أقسام مكتوبة الأنواع بقيم افتراضية، وإعدادات العميل في `deploy/tenants/<client>/settings.json` |
| التدقيق | كل عملية حساسة، إضافة فقط (trigger)، وعرض مفلتر بنطاق الفروع |
| الأحداث | Outbox في نفس الـ transaction، وناشر بـ SKIP LOCKED، ومستهلكون idempotent |
| القاعدة | ترحيل SQL صريح، ومستخدم تطبيق بأقل الصلاحيات و `statement_timeout` |
| التشغيل | Dockerfiles، و compose كامل (Postgres + pgBackRest، ونسختا Redis، و Celery)، و CI |

**الاختبارات:** 26 اختباراً على PostgreSQL 16 حقيقي، منها مطابقة الـ models للترحيل، وعزل الفروع (UAT-17)، وصلاحيات مستخدم التطبيق في القاعدة.

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
