# ReportZenE

Web app + MCP đọc **báo cáo sale Etsy của ZenE** từ `production.trackingis.info` và các **Lark Sheet báo cáo tay** của team.
Giao diện theo trackingis (Inter, xanh `#2563eb`, sidebar nhóm Etsy / Lark / System).

- Public: https://reportzene.trackingis.info (tunnel cloudflared `mba-system`, chung MBA)
- MCP cho agent: `https://reportzene.trackingis.info/mcp` (token cá nhân `rzn_…`)
- Stack: FastAPI + SQLite + Vue 3 / Element Plus / Highcharts (khung copy từ TM Check ACO)

## Chức năng

| Trang | Nội dung |
|---|---|
| Etsy › Report | 6 view giống trang Report Etsy của trackingis: Date (mở ra từng store), Order, Product, Store (mở ra từng ngày), Seller, Product type. Filter ngày, keyword, store, seller, designer, product type, sub product type, team, total order. Ô KPI: revenue, orders, quantity, AOV, total, sale tax. Chart + export CSV. |
| Etsy › Ornament | Doanh số Ornament theo **Product Type** của team, mở ra từng **Sub product type** (trackingis): Acrylic + Wood (Cutout Ornament, Ornament, Ornament 2-layers), Shell, Shaker, Ceramic (Shaped Ornament), Glass, Felt (Felt, Needle Felted), Others (Linen, Flat/Quilted Patchwork, Patchwork, Crochet, Wooden Garland). Orders, quantity, revenue, AOV, tỷ trọng revenue; chart cột chồng theo ngày; filter như Report; export CSV. Bảng phân loại nằm ở `backend/app/services/ornament.py`. Một đơn có nhiều loại được tính ở từng loại, nên tổng các dòng có thể hơi lớn hơn dòng tổng. |
| Etsy › Plan | Kế hoạch theo product: đọc khối bắt đầu ở **cột Q (17)** của sheet kế hoạch (tab "KH theo Product"), **11 product**: PL2/item, Total Sales, Total PL2, tỷ trọng, Sales/mo, Sales/day, PL2 từng tháng + dòng tổng của sheet. Ô KPI, chart theo tháng. Sheet / cột / số product chọn ở Settings › Plan; dữ liệu là bản Sync gần nhất. |
| Lark › Team sheets | Admin dán link Lark Sheet, chọn tab + hàng tiêu đề → Sync. Mọi người xem/tìm trong snapshot, bấm Sync để đọc lại. Chỉ đọc. |
| System › Settings | Token trackingis (mã hoá), team ZenE mặc định, Lark App ID/Secret, sheet kế hoạch (Plan), Test connections, Users (mở khoá / đổi role). |

## Nguồn dữ liệu trackingis

Gọi route internal `/api/v2` bằng **token của chính user**: SSO exchange của POD trả kèm `token`, app lưu mã hoá vào `users.pod_token` mỗi lần đăng nhập. Không có / hết hạn → dùng **token chung dự phòng** (admin dán ở Settings). MCP dùng token của chủ token `rzn_…`.

- `GET /etsy/report?view=…&from=…&to=…&page&per_page&sort_by&sort_order` + filter mảng `shops[] sellers[] designers[] product_types[] sub_product_types[] teams[]`, text `keyword total_order symbol`.
- KPI = cộng các dòng view `date` (route `/etsy/report/totals` của trackingis đang trả 500). View `date` trả tối đa 31 ngày/trang nên tự lật trang.
- Filter dropdown: `/filter/shop?platform=etsy`, `/filter/seller?platform[]=etsy`, `/filter/designers`, `/filter/product-type?platform=etsy`, `/filter/sub-product-type?platform=etsy`, `/filter/teams`.
- Team ZenE: BU `ZenE` id 9; team Etsy 1/2/3.ZenE = 12/13/23. Mặc định lọc theo danh sách ở Settings; `teams=` rỗng = mọi team.
- Cloudflare chặn User-Agent mặc định của python → client luôn gửi UA `reportzene/…`.
- Token hết hạn → trackingis trả 401 → app báo "dán token mới ở Settings". Lấy token: web trackingis → avatar → Extension Token (60s) → `POST /api/v2/vault/auth/extension-login`.

## Đăng nhập

- **SSO POD** (Sign in with Isuccess System): app SSO **riêng** của ReportZenE (key `3wsqtk6scx8p6sne`, tạo 17/10/2026),
  redirect `https://reportzene.trackingis.info/auth/pod/callback`. Secret chỉ nằm trong plist launchd.
- Dữ liệu doanh số nên SSO lần đầu tạo user **bị khoá**, trừ email trong `POD_ALLOWED_USERS` (plist launchd). Admin mở khoá ở Settings › Users.
- Admin mật khẩu dự phòng: tạo lần deploy đầu, mật khẩu ở `~/reportzene/.admin-password` trên server.

## MCP

Menu avatar → *Agent tokens (MCP)* → tạo token, rồi:

```bash
claude mcp add --scope user --transport http reportzene https://reportzene.trackingis.info/mcp --header "Authorization: Bearer rzn_…"
```

Tool (chỉ đọc): `whoami`, `etsy_totals`, `etsy_report`, `etsy_ornament`, `filter_options`, `list_sheets`, `read_sheet`, `sync_sheet`.

## Chạy local

```bash
cd backend && uv sync && PYTHONPATH=. uv run python scripts/create_user.py you@example.com "Tên" CODE admin
uv run uvicorn app.main:app --port 8871        # API + MCP
cd ../web && npm install && npm run dev        # http://localhost:5177 (proxy → 8871)
cd ../backend && uv run pytest -q              # 50 test
```

## Deploy

**Tự động (mặc định):** push / merge vào `main` là đủ. Trên macminiwork, launchd `com.isuccess.reportzene-autodeploy`
chạy `deploy/autodeploy.sh` mỗi phút: thấy commit mới → `pytest` → build web → rsync sang `~/reportzene` → restart → health check.
Test hoặc build lỗi thì **không deploy** commit đó (và không thử lại tới khi có commit mới).
Xem kết quả: `ssh macminiwork tail -20 ~/reportzene-autodeploy/autodeploy.log` (log test/build: `last_tests.log`, `last_build.log`).
Clone dùng deploy key read-only `~/.ssh/reportzene_deploy` (host alias `github-reportzene`).

**Tay** (khi cần đổi plist launchd: SSO key/secret, allow-list):

`bash deploy/deploy.sh` → test + build → rsync lên macminiwork `~/reportzene` → launchd `online.kntmcptools.reportzene`,
uvicorn `100.96.215.29:8870`. Key/secret SSO được giữ trong plist qua mỗi lần deploy (đổi: `POD_APP_KEY=… POD_APP_SECRET=… bash deploy/deploy.sh`).

Tunnel: ingress `reportzene.trackingis.info → http://100.96.215.29:8870` trong `~/.cloudflared/mba-system.yml` (backup `.bak-reportzene-*`),
CNAME tạo bằng `cloudflared tunnel route dns mba-system reportzene.trackingis.info`. Restart tunnel = MBA gián đoạn vài giây.
