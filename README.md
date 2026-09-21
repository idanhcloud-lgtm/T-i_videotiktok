# Tải video Douyin / TikTok (dùng riêng)

Web app có mật khẩu, tối ưu cho Safari trên iPhone. Mã nguồn không chứa mật khẩu hay cookie.

## Chạy trên máy tính

1. Cài dependencies: `py -m pip install -r requirements.txt`
2. Tạo file `.env` từ `.env.example`, rồi đặt `APP_PASSWORD` và `SECRET_KEY`.
3. Nạp các biến môi trường và chạy: `py app.py`

## Deploy

Thiết lập các environment variables `APP_PASSWORD` và `SECRET_KEY` trên dịch vụ deploy. Nếu cần Douyin, đặt file `cookies.txt` vào vùng secret/volume của máy chủ và trỏ `COOKIE_FILE` tới file đó. Không commit cookie, `.env`, hay thư mục `downloads`.

Lệnh start cho các dịch vụ hỗ trợ Gunicorn: `gunicorn --bind 0.0.0.0:$PORT app:app`

Gunicorn tự đọc `gunicorn.conf.py` trong repo, nên không cần thêm tham số vào lệnh start. File này nâng timeout lên 300 giây: video được tải ngay trong request, và timeout mặc định 30 giây của Gunicorn giết worker giữa chừng khiến trang trả về `Internal Server Error`.

## Lưu ý

- Đây là app cho hai người dùng tin cậy. Không chia sẻ mật khẩu hoặc URL nếu chưa cần thiết.
- Douyin có thể từ chối IP cloud hoặc yêu cầu cập nhật cookie theo thời gian.
- File tải về được tự dọn sau tối đa hai giờ kể từ lần có request tiếp theo.
