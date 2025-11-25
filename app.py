from flask import Flask, request, jsonify, render_template, Response, redirect, url_for
from flask_cors import CORS
import sqlite3
from datetime import datetime
import os
import io
import csv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "games.db")



def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    # 개인전 게임 기록 (4인 마작)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            player1_name TEXT NOT NULL,
            player2_name TEXT NOT NULL,
            player3_name TEXT NOT NULL,
            player4_name TEXT NOT NULL,
            player1_score INTEGER NOT NULL,
            player2_score INTEGER NOT NULL,
            player3_score INTEGER NOT NULL,
            player4_score INTEGER NOT NULL
        )
    """)

    # 팀 목록
    conn.execute("""
        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    """)

    # 팀원 매핑
    conn.execute("""
        CREATE TABLE IF NOT EXISTS team_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            team_name TEXT NOT NULL,
            player_name TEXT NOT NULL,
            joined_at TEXT NOT NULL
        )
    """)

    # 팀전 게임 기록
    conn.execute("""
        CREATE TABLE IF NOT EXISTS team_games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            p1_player_name TEXT NOT NULL,
            p1_team_name   TEXT NOT NULL,
            p1_score       INTEGER NOT NULL,
            p2_player_name TEXT NOT NULL,
            p2_team_name   TEXT NOT NULL,
            p2_score       INTEGER NOT NULL,
            p3_player_name TEXT NOT NULL,
            p3_team_name   TEXT NOT NULL,
            p3_score       INTEGER NOT NULL,
            p4_player_name TEXT NOT NULL,
            p4_team_name   TEXT NOT NULL,
            p4_score       INTEGER NOT NULL
        )
    """)

    conn.commit()
    conn.close()


app = Flask(__name__, static_folder="static", template_folder="templates")
CORS(app)
init_db()

# 마작 포인트 계산용 상수 (개인/팀 공통)
UMA_VALUES = [50, 10, -10, -30]   # 1등~4등 우마 (+오카 반영한 버전)
RETURN_SCORE = 30000


# ================== 개인전 API ==================

@app.route("/api/games", methods=["GET"])
def list_games():
    conn = get_db()
    cur = conn.execute("SELECT * FROM games ORDER BY id DESC")
    rows = cur.fetchall()
    conn.close()
    return jsonify([dict(row) for row in rows])


@app.route("/api/games", methods=["POST"])
def create_game():
    data = request.get_json() or {}

    required = [
        "player1_name", "player2_name", "player3_name", "player4_name",
        "player1_score", "player2_score", "player3_score", "player4_score",
    ]
    if not all(k in data for k in required):
        return jsonify({"error": "missing fields"}), 400

    p1 = str(data["player1_name"]).strip()
    p2 = str(data["player2_name"]).strip()
    p3 = str(data["player3_name"]).strip()
    p4 = str(data["player4_name"]).strip()
    if not (p1 and p2 and p3 and p4):
        return jsonify({"error": "all player names required"}), 400

    try:
        s1 = int(data["player1_score"])
        s2 = int(data["player2_score"])
        s3 = int(data["player3_score"])
        s4 = int(data["player4_score"])
    except (ValueError, TypeError):
        return jsonify({"error": "scores must be integers"}), 400

    created_at = datetime.now().isoformat(timespec="minutes")

    conn = get_db()
    cur = conn.execute("""
        INSERT INTO games (
            created_at,
            player1_name, player2_name, player3_name, player4_name,
            player1_score, player2_score, player3_score, player4_score
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (created_at, p1, p2, p3, p4, s1, s2, s3, s4))
    conn.commit()
    new_id = cur.lastrowid
    conn.close()

    return jsonify({"id": new_id}), 201


@app.route("/api/games/<int:game_id>", methods=["DELETE"])
def delete_game(game_id):
    conn = get_db()
    cur = conn.execute("DELETE FROM games WHERE id = ?", (game_id,))
    conn.commit()
    deleted = cur.rowcount
    conn.close()

    if deleted == 0:
        return jsonify({"error": "not found"}), 404
    return jsonify({"ok": True})


# ---- 개인전 CSV 내보내기 ----

@app.route("/export", methods=["GET"])
def export_games():
    conn = get_db()
    cur = conn.execute("""
        SELECT
            id, created_at,
            player1_name, player2_name, player3_name, player4_name,
            player1_score, player2_score, player3_score, player4_score
        FROM games
        ORDER BY id ASC
    """)
    rows = cur.fetchall()
    conn.close()

    # pts 계산용 함수 (프론트랑 똑같이)
    def calc_pts(scores):
        # scores: [s1, s2, s3, s4]
        order = sorted(range(4), key=lambda i: scores[i], reverse=True)

        uma_for_player = [0, 0, 0, 0]
        for rank, idx in enumerate(order):
            uma_for_player[idx] = UMA_VALUES[rank]  # 전역에 정의된 [50,10,-10,-30]

        pts = []
        for i in range(4):
            base = (scores[i] - RETURN_SCORE) / 1000.0  # RETURN_SCORE = 30000
            pts.append(base + uma_for_player[i])
        return pts

    import io
    import csv

    output = io.StringIO()
    writer = csv.writer(output)

    # 🔹 헤더: 네가 보내준 형식 그대로
    writer.writerow([
        "ID", "시간",
        "P1 이름", "P1 점수", "P1 pt",
        "P2 이름", "P2 점수", "P2 pt",
        "P3 이름", "P3 점수", "P3 pt",
        "P4 이름", "P4 점수", "P4 pt",
    ])

    for row in rows:
        s1 = row["player1_score"]
        s2 = row["player2_score"]
        s3 = row["player3_score"]
        s4 = row["player4_score"]
        scores = [s1, s2, s3, s4]
        pts = calc_pts(scores)  # [pt1, pt2, pt3, pt4]

        writer.writerow([
            row["id"],
            row["created_at"],
            row["player1_name"], s1, f"{pts[0]:.1f}",
            row["player2_name"], s2, f"{pts[1]:.1f}",
            row["player3_name"], s3, f"{pts[2]:.1f}",
            row["player4_name"], s4, f"{pts[3]:.1f}",
        ])

    csv_data = output.getvalue()
    output.close()

    # 🔥 엑셀 호환을 위해 CP949(ANSI)로 인코딩
    csv_bytes = csv_data.encode("cp949", errors="replace")

    from flask import Response
    return Response(
        csv_bytes,
        mimetype="text/csv; charset=cp949",
        headers={
            "Content-Disposition": "attachment; filename=madang_majhong_rating.csv"
        },
    )



# ---- 개인전 CSV 업로드 ----

@app.route("/import", methods=["GET", "POST"])
def import_games():
    if request.method == "GET":
        # 업로드 페이지
        return """
        <!DOCTYPE html>
        <html lang="ko">
        <head>
          <meta charset="UTF-8">
          <title>개인전 CSV 업로드</title>
          <link rel="stylesheet" href="/static/style.css">
        </head>
        <body>
          <div class="top-bar">
            <h1>개인전 CSV 업로드</h1>
            <div class="view-switch">
              <a href="/" class="view-switch-btn">메인으로 돌아가기</a>
            </div>
          </div>
          <div class="main-layout">
            <div class="left-panel">
              <section class="games-panel">
                <h2>개인전 CSV 업로드</h2>
                <p class="hint-text">
                  * /export 에서 받은 games.csv 나<br>
                  * ID / 시간 / P1 이름 / P1 점수 / ... 형식의 파일 모두 인식합니다.
                </p>
                <form method="post" enctype="multipart/form-data">
                  <p><input type="file" name="file" accept=".csv" required></p>
                  <p><button type="submit">업로드</button></p>
                </form>
              </section>
            </div>
          </div>
        </body>
        </html>
        """

    file = request.files.get("file")
    if not file:
        return "파일이 없습니다.", 400

    # 1) 인코딩 대충 자동 감지 (utf-8 / cp949 우선)
    raw = file.read()
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp949"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue

    if text is None:
        return "알 수 없는 인코딩입니다. UTF-8 또는 CP949로 저장해주세요.", 400

    # 2) 구분자 자동 감지(, 또는 ;)
    import io as _io
    sample = "\n".join(text.splitlines()[:5])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;")
    except Exception:
        dialect = csv.excel
        dialect.delimiter = ","

    reader = csv.DictReader(_io.StringIO(text), dialect=dialect)

    def pick(row, keys, default=""):
        """여러 후보 키 중 먼저 나오는 값 사용"""
        for k in keys:
            if k in row and row[k] not in (None, ""):
                return row[k]
        return default

    def pick_int(row, keys, default=0):
        val = pick(row, keys, None)
        if val is None or val == "":
            return default
        try:
            return int(float(val))
        except (ValueError, TypeError):
            return default

    conn = get_db()
    inserted = 0

    for row in reader:
        # 시간 / created_at
        created_at = pick(row, ["created_at", "시간"])
        if not created_at:
            created_at = datetime.now().isoformat(timespec="minutes")

        # 이름/점수 매핑 (영문 헤더 + 한글 헤더 둘 다 지원)
        p1_name = pick(row, ["player1_name", "P1 이름", "P1이름"])
        p2_name = pick(row, ["player2_name", "P2 이름", "P2이름"])
        p3_name = pick(row, ["player3_name", "P3 이름", "P3이름"])
        p4_name = pick(row, ["player4_name", "P4 이름", "P4이름"])

        s1 = pick_int(row, ["player1_score", "P1 점수", "P1점수"])
        s2 = pick_int(row, ["player2_score", "P2 점수", "P2점수"])
        s3 = pick_int(row, ["player3_score", "P3 점수", "P3점수"])
        s4 = pick_int(row, ["player4_score", "P4 점수", "P4점수"])

        # 이름이 하나도 없으면 애매하니까 스킵
        if not (p1_name or p2_name or p3_name or p4_name):
            continue

        conn.execute("""
            INSERT INTO games (
                created_at,
                player1_name, player2_name, player3_name, player4_name,
                player1_score, player2_score, player3_score, player4_score
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (created_at,
              p1_name, p2_name, p3_name, p4_name,
              s1, s2, s3, s4))
        inserted += 1

    conn.commit()
    conn.close()

    print(f"[IMPORT] inserted rows: {inserted}")
    return redirect(url_for("index_page"))

# ================== 기본 페이지 ==================

@app.route("/")
def index_page():
    return render_template("index.html")


if __name__ == "__main__":
    if not os.path.exists(DB_PATH):
        init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
