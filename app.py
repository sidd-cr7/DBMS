from flask import Flask, request, jsonify, render_template
import mysql.connector
from mysql.connector import Error
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# Database configuration
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': 'siddu1232006',
    'database': 'ResumeShortlisting'
}

def recalculate_score_for_candidate(conn, cid):
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM Candidate WHERE candidate_id = %s", (cid,))
    candidate = cursor.fetchone()

    cursor.execute("SELECT * FROM Skills WHERE candidate_id = %s", (cid,))
    skills = cursor.fetchall()

    cursor.execute("SELECT * FROM Certifications WHERE candidate_id = %s", (cid,))
    certs = cursor.fetchall()

    cursor.execute("SELECT * FROM RankingWeights LIMIT 1")
    weights = cursor.fetchone()

    exp_score = min(candidate['experience'], 10) / 10.0
    edu_score_map = {'PhD': 1.0, 'Master': 0.8, 'Bachelor': 0.6, 'Diploma': 0.4, 'Other': 0.2}
    edu_score = edu_score_map.get(candidate['education_level'], 0.2)

    skill_score = (sum(skill['proficiency_level'] for skill in skills) / len(skills) / 10.0) if skills else 0.0
    cert_score = (min(sum(cert['validity_years'] for cert in certs), 10) / 10.0) if certs else 0.0

    total = (exp_score * weights['experience_weight'] +
             edu_score * weights['education_weight'] +
             skill_score * weights['skill_weight'] +
             cert_score * weights['certification_weight'])

    cursor.execute("UPDATE Candidate SET total_score = %s WHERE candidate_id = %s", (total, cid))
    conn.commit()
    cursor.close()

# HTML Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/add')
def add_page():
    return render_template('add.html')

@app.route('/delete')
def delete_page():
    return render_template('delete.html')

@app.route('/display')
def display_page():
    return render_template('display.html')

@app.route('/sort')
def sort_page():
    return render_template('sort.html')

@app.route('/search_page')
def search_page():
    return render_template('search.html')

# API Routes
@app.route('/api/candidates', methods=['GET'])
def get_all_candidates():
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        query = """
            SELECT c.*, 
                GROUP_CONCAT(DISTINCT CONCAT(s.skill_name, ' (', s.proficiency_level, ')')) AS skills,
                GROUP_CONCAT(DISTINCT CONCAT(cert.certification_name, ' - ', cert.issuing_organization, ' (', cert.validity_years, ' yrs)')) AS certifications
            FROM Candidate c
            LEFT JOIN Skills s ON c.candidate_id = s.candidate_id
            LEFT JOIN Certifications cert ON c.candidate_id = cert.candidate_id
            GROUP BY c.candidate_id
        """
        cursor.execute(query)
        return jsonify(cursor.fetchall())
    except Error as e:
        return jsonify({'error': str(e)})
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

@app.route('/api/candidates/sorted', methods=['GET'])
def get_sorted_candidates():
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM Candidate ORDER BY total_score DESC")
        return jsonify(cursor.fetchall())
    except Error as e:
        return jsonify({'error': str(e)})
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

@app.route('/candidates', methods=['POST'])
def add_candidate():
    data = request.json
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        # Insert into Candidate table
        cursor.execute("""
            INSERT INTO Candidate (name, email, phone, experience, education_level)
            VALUES (%s, %s, %s, %s, %s)
        """, (data['name'], data['email'], data['phone'], data['experience'], data['education_level']))
        candidate_id = cursor.lastrowid

        # Insert Skills
        for skill in data.get('skills', []):
            cursor.execute("""
                INSERT INTO Skills (candidate_id, skill_name, proficiency_level)
                VALUES (%s, %s, %s)
            """, (candidate_id, skill['skill_name'], skill['proficiency_level']))

        # Insert Certifications
        for cert in data.get('certifications', []):
            cursor.execute("""
                INSERT INTO Certifications (candidate_id, certification_name, issuing_organization, validity_years)
                VALUES (%s, %s, %s, %s)
            """, (candidate_id, cert['certification_name'], cert['issuing_organization'], cert['validity_years']))

        conn.commit()

        # Optional: Recalculate score after adding
        recalculate_score_for_candidate(conn, candidate_id)

        return jsonify({'message': 'Candidate added successfully'}), 201
    except Error as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

@app.route('/delete', methods=['POST'])
def delete_candidate():
    # Get JSON data from the request
    data = request.get_json()
    candidate_id = data.get('candidate_id')

    if not candidate_id:
        return jsonify({'error': 'Candidate ID is required'}), 400

    try:
        # Connect to the database
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor()

        # Execute the delete query
        cursor.execute("DELETE FROM Candidate WHERE candidate_id = %s", (candidate_id,))
        conn.commit()

        # Check if the candidate was found and deleted
        if cursor.rowcount == 0:
            return jsonify({'message': f'No candidate found with ID {candidate_id}'}), 404
        else:
            return jsonify({'message': f'Candidate with ID {candidate_id} deleted successfully'}), 200

    except mysql.connector.Error as e:
        return jsonify({'error': str(e)}), 500

    finally:
        # Close the database connection
        if conn.is_connected():
            cursor.close()
            conn.close()


@app.route('/search', methods=['GET'])
def search_candidates():
    skill = request.args.get('skill')
    min_experience = request.args.get('experience', 0, type=int)

    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)

        query = """
            SELECT DISTINCT c.*
            FROM Candidate c
            JOIN Skills s ON c.candidate_id = s.candidate_id
            WHERE s.skill_name LIKE %s AND c.experience >= %s
        """
        cursor.execute(query, ('%' + skill + '%', min_experience))
        results = cursor.fetchall()
        return jsonify(results)
    except Error as e:
        return jsonify({'error': str(e)})
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

@app.route('/recalculate_scores', methods=['POST'])
def recalculate_scores():
    try:
        conn = mysql.connector.connect(**db_config)
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM RankingWeights LIMIT 1")
        weights = cursor.fetchone()
        exp_w, edu_w, skill_w, cert_w = (
            weights['experience_weight'],
            weights['education_weight'],
            weights['skill_weight'],
            weights['certification_weight']
        )

        cursor.execute("SELECT * FROM Candidate")
        candidates = cursor.fetchall()

        for candidate in candidates:
            cid = candidate['candidate_id']
            exp_score = min(candidate['experience'], 10) / 10

            edu_levels = {'PhD': 1.0, 'Master': 0.8, 'Bachelor': 0.6, 'Diploma': 0.4, 'Other': 0.2}
            edu_score = edu_levels.get(candidate['education_level'], 0)

            cursor.execute("SELECT AVG(proficiency_level) AS avg_skill FROM Skills WHERE candidate_id = %s", (cid,))
            skill_score = cursor.fetchone()['avg_skill'] or 0
            skill_score /= 10

            cursor.execute("SELECT SUM(validity_years) AS cert_score FROM Certifications WHERE candidate_id = %s", (cid,))
            cert_score = cursor.fetchone()['cert_score'] or 0
            cert_score = min(cert_score, 10) / 10

            total = (
                exp_score * exp_w +
                edu_score * edu_w +
                skill_score * skill_w +
                cert_score * cert_w
            )

            cursor.execute("UPDATE Candidate SET total_score = %s WHERE candidate_id = %s", (total, cid))

        conn.commit()
        return jsonify({'message': 'Scores recalculated successfully'})
    except Error as e:
        return jsonify({'error': str(e)})
    finally:
        if conn.is_connected():
            cursor.close()
            conn.close()

if __name__ == '__main__':
    app.run(debug=True, port=5001)
