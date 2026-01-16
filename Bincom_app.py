from flask import Flask, request, render_template_string
import pymysql

app = Flask(__name__)

DB_CONFIG = dict(
    host="localhost",
    user="root",             
    password="Yahoomail200",
    database="bincom_test",
    cursorclass=pymysql.cursors.DictCursor
)

def db():
    return pymysql.connect(**DB_CONFIG)

# -------------------------------
# Homepage
# -------------------------------
@app.route("/")
def home():
    return """
    <h2>Bincom Election Demo</h2>
    <ul>
      <li><a href="/polling-unit">Question 1: Polling Unit Results</a></li>
      <li><a href="/lga-results">Question 2: LGA Summed Results</a></li>
      <li><a href="/new-polling-unit">Question 3: Add New Polling Unit</a></li>
    </ul>
    """

# -------------------------------
# Question 1: Polling Unit Results
# -------------------------------
@app.route("/polling-unit")
def polling_unit():
    TPL = """
    <h3>Question 1: Display results for a polling unit</h3>
    <form method="get">
      <label>Polling Unit Unique ID:</label>
      <input type="number" name="pu_uniqueid" value="{{ pu_uniqueid or '' }}" required>
      <button type="submit">Show Results</button>
    </form>

    {% if results is not none %}
      {% if results %}
        <h4>Results for Polling Unit Unique ID: {{ pu_uniqueid }}</h4>
        <table border="1" cellpadding="6">
          <tr><th>Party</th><th>Score</th></tr>
          {% for row in results %}
            <tr><td>{{ row.party_abbreviation }}</td><td>{{ row.party_score }}</td></tr>
          {% endfor %}
        </table>
      {% else %}
        <p>No results found for this polling unit.</p>
      {% endif %}
    {% endif %}

    <p><a href="/">Back to Home</a></p>
    """
    pu_uniqueid = request.args.get("pu_uniqueid", type=int)
    results = None
    if pu_uniqueid is not None:
        with db() as conn, conn.cursor() as cur:
            cur.execute("""
                SELECT party_abbreviation, party_score
                FROM announced_pu_results
                WHERE polling_unit_uniqueid = %s
                ORDER BY party_abbreviation
            """, (pu_uniqueid,))
            results = cur.fetchall()
    return render_template_string(TPL, pu_uniqueid=pu_uniqueid, results=results)

# -------------------------------
# Question 2: LGA Summed Results
# -------------------------------
@app.route("/lga-results")
def lga_results():
    TPL = """
    <h3>Question 2: Summed total of all polling units under an LGA</h3>
    <form method="get">
      <label>Select Local Government:</label>
      <select name="lga_id" required>
        <option value="">-- choose LGA --</option>
        {% for lga in lgas %}
          <option value="{{ lga.lga_id }}" {% if lga_id == lga.lga_id %}selected{% endif %}>{{ lga.lga_name }}</option>
        {% endfor %}
      </select>
      <button type="submit">Compute</button>
    </form>

    {% if totals is not none %}
      {% if totals %}
        <h4>Summed Results for LGA: {{ lga_name }}</h4>
        <table border="1" cellpadding="6">
          <tr><th>Party</th><th>Total Score</th></tr>
          {% for row in totals %}
            <tr><td>{{ row.party_abbreviation }}</td><td>{{ row.total_score }}</td></tr>
          {% endfor %}
        </table>
      {% else %}
        <p>No polling unit results found under this LGA.</p>
      {% endif %}
    {% endif %}

    <p><a href="/">Back to Home</a></p>
    """
    # Load LGAs in Delta State (state_id = 25)
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT lga_id, lga_name FROM lga WHERE state_id = 25 ORDER BY lga_name")
        lgas = cur.fetchall()

    lga_id = request.args.get("lga_id", type=int)
    totals = None
    lga_name = None

    if lga_id:
        with db() as conn, conn.cursor() as cur:
            cur.execute("SELECT lga_name FROM lga WHERE lga_id = %s", (lga_id,))
            row = cur.fetchone()
            lga_name = row["lga_name"] if row else f"LGA {lga_id}"

            cur.execute("""
                SELECT apr.party_abbreviation, SUM(apr.party_score) AS total_score
                FROM polling_unit pu
                JOIN announced_pu_results apr
                  ON pu.uniqueid = apr.polling_unit_uniqueid
                WHERE pu.lga_id = %s
                GROUP BY apr.party_abbreviation
                ORDER BY apr.party_abbreviation
            """, (lga_id,))
            totals = cur.fetchall()

    return render_template_string(TPL, lgas=lgas, lga_id=lga_id, totals=totals, lga_name=lga_name)

# -------------------------------
# Question 3: Add New Polling Unit
# -------------------------------
@app.route("/new-polling-unit", methods=["GET", "POST"])
def new_polling_unit():
    TPL = """
    <h3>Question 3: Add a New Polling Unit</h3>
    <form method="post">
      <label>Polling Unit Name:</label>
      <input type="text" name="pu_name" required><br><br>

      <label>Ward ID:</label>
      <input type="number" name="ward_id" required><br><br>

      <label>LGA ID:</label>
      <input type="number" name="lga_id" required><br><br>

      <h4>Enter Party Scores</h4>
      {% for party in parties %}
        <label>{{ party.partyname }} ({{ party.partyid }}):</label>
        <input type="number" name="score_{{ party.partyid }}" value="0"><br>
      {% endfor %}

      <br><button type="submit">Save Results</button>
    </form>

    {% if message %}
      <p><b>{{ message }}</b></p>
    {% endif %}

    <p><a href="/">Back to Home</a></p>
    """
    message = None

    # Load all parties
    with db() as conn, conn.cursor() as cur:
        cur.execute("SELECT partyid, partyname FROM party ORDER BY partyid")
        parties = cur.fetchall()

    if request.method == "POST":
        pu_name = request.form["pu_name"]
        ward_id = request.form["ward_id"]
        lga_id = request.form["lga_id"]

        with db() as conn, conn.cursor() as cur:
            # ✅ Fix: generate a new polling_unit_id manually
            cur.execute("SELECT MAX(polling_unit_id) AS max_id FROM polling_unit")
            row = cur.fetchone()
            next_id = (row["max_id"] or 0) + 1

            # Insert new polling unit with required fields
            cur.execute("""
                INSERT INTO polling_unit (
                    polling_unit_id, polling_unit_name, ward_id, lga_id,
                    entered_by_user, date_entered, user_ip_address
                )
                VALUES (%s, %s, %s, %s, %s, NOW(), %s)
            """, (next_id, pu_name, ward_id, lga_id, "system", "127.0.0.1"))

            new_pu_id = next_id

            # Insert results for each party
            for party in parties:
                score = request.form.get(f"score_{party['partyid']}", 0)
                cur.execute("""
                    INSERT INTO announced_pu_results (polling_unit_uniqueid, party_abbreviation, party_score)
                    VALUES (%s, %s, %s)
                """, (new_pu_id, party["partyid"], score))

            conn.commit()
            message = f"New polling unit '{pu_name}' added with results!"

    return render_template_string(TPL, parties=parties, message=message)

# -------------------------------
# Run the app
# -------------------------------
if __name__ == "__main__":
    app.run(debug=True)
