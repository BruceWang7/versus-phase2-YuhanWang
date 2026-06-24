######################################
# VERSUS skeleton app.py
# CS460 Final Project
######################################
# Covers the core: register/login, create bracket, browse, view.
# Students extend with: predictions, voting, round-closing (stored
# procedure), triggers, leaderboard (window functions), recursive CTE,
# follows, comments, indexes.
###################################################

import flask
from flask import Flask, request, render_template, redirect, url_for
import mysql.connector
import flask_login
import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'super secret string'  # Change this!

# These will need to be changed according to your credentials.
DB_USER     = 'root'
DB_PASSWORD = 'Wang050804'
DB_NAME     = 'versus'
DB_HOST     = 'localhost'

def get_conn():
	return mysql.connector.connect(
		host=DB_HOST,
		user=DB_USER,
		password=DB_PASSWORD,
		database=DB_NAME,
		autocommit=False,
	)

conn = get_conn()


# begin code used for login
login_manager = flask_login.LoginManager()
login_manager.init_app(app)


def getUserList():
	cursor = conn.cursor()
	cursor.execute("SELECT username from Users")
	rows = cursor.fetchall()
	cursor.close()
	return rows


class User(flask_login.UserMixin):
	pass


@login_manager.user_loader
def user_loader(username):
	users = getUserList()
	if not(username) or username not in str(users):
		return
	user = User()
	user.id = username
	return user


@login_manager.request_loader
def request_loader(request):
	users = getUserList()
	username = request.form.get('username')
	if not(username) or username not in str(users):
		return
	user = User()
	user.id = username
	cursor = conn.cursor()
	cursor.execute("SELECT password FROM Users WHERE username = '{0}'".format(username))
	data = cursor.fetchall()
	cursor.close()
	pwd = str(data[0][0])
	user.is_authenticated = check_password_hash(pwd, request.form['password'])
	return user


'''
A new page looks like this:
@app.route('new_page_name')
def new_page_function():
	return new_page_html
'''

@app.route('/login', methods=['GET', 'POST'])
def login():
	if request.method == 'GET':
		return '''
			<form action='login' method='POST'>
				<input type='text' name='username' id='username' placeholder='username' />
				<input type='password' name='password' id='password' placeholder='password' />
				<input type='submit' name='submit' />
			</form><br />
			<a href='/'>Home</a>
		'''
	# The request method is POST (page is receiving data)
	username = request.form['username']
	cursor = conn.cursor()
	# check if username is registered
	cursor.execute("SELECT password FROM Users WHERE username = '{0}'".format(username))
	data = cursor.fetchall()
	cursor.close()
	if data:
		pwd = str(data[0][0])
		if check_password_hash(pwd, request.form['password']):
			user = User()
			user.id = username
			flask_login.login_user(user)
			return redirect(url_for('home'))
	# information did not match
	return "<a href='/login'>Try again</a><br />\
			<a href='/register'>or make an account</a>"


@login_manager.unauthorized_handler
def unauthorized_handler():
	return render_template('unauth.html')


# you can specify specific methods (GET/POST) in the function header instead
# of inside the function body
@app.route("/register", methods=['GET'])
def register():
	return render_template('register.html')


@app.route("/register", methods=['POST'])
def register_user():
	try:
		username = request.form.get('username')
		email    = request.form.get('email')
		password = request.form.get('password')
		password_hash = generate_password_hash(password)
		bio      = request.form.get('bio')
	except:
		print("couldn't find all tokens")
		return redirect(url_for('register'))
	cursor = conn.cursor()
	if isUsernameUnique(username) and isEmailUnique(email):
		cursor.execute(
    		"INSERT INTO Users (username, email, password, bio) VALUES ('{0}', '{1}', '{2}', '{3}')".format(
        		username, email, password_hash, bio or ""))
		conn.commit()
		cursor.close()
		# log user in
		user = User()
		user.id = username
		flask_login.login_user(user)
		return render_template('hello.html', name=username, message='account created')
	else:
		cursor.close()
		return "Username or email already in use<br><a href='/register'>Try again</a>"


def isUsernameUnique(username):
	# use this to check if a username has already been registered
	cursor = conn.cursor()
	cursor.execute("SELECT username FROM Users WHERE username = '{0}'".format(username))
	rows = cursor.fetchall()
	cursor.close()
	return len(rows) == 0


def isEmailUnique(email):
	cursor = conn.cursor()
	cursor.execute("SELECT email FROM Users WHERE email = '{0}'".format(email))
	rows = cursor.fetchall()
	cursor.close()
	return len(rows) == 0


def getUserIdFromUsername(username):
	cursor = conn.cursor()
	cursor.execute("SELECT user_id FROM Users WHERE username = '{0}'".format(username))
	row = cursor.fetchone()
	cursor.close()
	return row[0] if row else None


def getUsernameFromUserId(uid):
	cursor = conn.cursor()
	cursor.execute("SELECT username FROM Users WHERE user_id = '{0}'".format(uid))
	row = cursor.fetchone()
	cursor.close()
	return row[0] if row else None

# end login code


# begin bracket creation code
@app.route('/create', methods=['GET', 'POST'])
@flask_login.login_required
def create_bracket():
	if request.method == 'POST':
		uid           = getUserIdFromUsername(flask_login.current_user.id)
		title         = request.form.get('title')
		description   = request.form.get('description')
		entrant_count = int(request.form.get('entrant_count'))
		cursor = conn.cursor()

		try:
			# 1. insert the bracket row
			cursor.execute(
				"INSERT INTO Brackets (host_id, title, description, entrant_count) VALUES ('{0}', '{1}', '{2}', '{3}')".format(
					uid, title, description or "", entrant_count))
			cursor.execute("SELECT LAST_INSERT_ID()")
			bracket_id = cursor.fetchone()[0]

			# 2. insert all entrants in seed order
			entrant_ids = []
			for seed in range(1, entrant_count + 1):
				entrant_name = request.form.get('entrant_' + str(seed))
				cursor.execute(
					"INSERT INTO Entrants (bracket_id, seed, name) VALUES ('{0}', '{1}', '{2}')".format(
						bracket_id, seed, entrant_name))
				cursor.execute("SELECT LAST_INSERT_ID()")
				entrant_ids.append(cursor.fetchone()[0])

			# 3. create Round 1 matchups
			round_1_slots = entrant_count // 2
			for slot in range(1, round_1_slots + 1):
				a = entrant_ids[(slot - 1) * 2]
				b = entrant_ids[(slot - 1) * 2 + 1]
				cursor.execute(
					"INSERT INTO Matchups (bracket_id, round, slot, entrant_a_id, entrant_b_id) VALUES ('{0}', 1, '{1}', '{2}', '{3}')".format(
						bracket_id, slot, a, b))

			# 4. create empty shells for later rounds
			slots = round_1_slots // 2
			round_num = 2
			while slots >= 1:
				for slot in range(1, slots + 1):
					cursor.execute(
						"INSERT INTO Matchups (bracket_id, round, slot) VALUES ('{0}', '{1}', '{2}')".format(
							bracket_id, round_num, slot))
				slots //= 2
				round_num += 1

			conn.commit()
			cursor.close()
			return redirect(url_for('view_bracket', bracket_id=bracket_id))

		except Exception as e:
			conn.rollback()
			cursor.close()
			return "Create bracket failed: {0}<br><a href='/create'>Try again</a>".format(e)
	else:
		return render_template('create.html')
# end bracket creation code


# begin browse code
def getAllBrackets():
	cursor = conn.cursor()
	cursor.execute(
		"SELECT b.bracket_id, b.title, b.status, b.entrant_count, b.created_at, u.username "
		"FROM Brackets b JOIN Users u ON b.host_id = u.user_id "
		"ORDER BY b.created_at DESC")
	rows = cursor.fetchall()
	cursor.close()
	return rows


@app.route('/browse', methods=['GET'])
def browse():
	brackets = getAllBrackets()
	return render_template('browse.html', brackets=brackets)
# end browse code


# begin bracket view code
def getBracketInfo(bracket_id):
	cursor = conn.cursor()
	cursor.execute(
		"SELECT b.bracket_id, b.title, b.description, b.status, b.entrant_count, u.username, b.host_id "
		"FROM Brackets b JOIN Users u ON b.host_id = u.user_id "
		"WHERE b.bracket_id = '{0}'".format(bracket_id))
	row = cursor.fetchone()
	cursor.close()
	return row


def getMatchupsForBracket(bracket_id):
	cursor = conn.cursor()
	cursor.execute(
		"SELECT m.matchup_id, m.round, m.slot, "
		"m.entrant_a_id, ea.name, "
		"m.entrant_b_id, eb.name, "
		"m.winner_entrant_id, ew.name, "
		"m.votes_a, m.votes_b "
		"FROM Matchups m "
		"LEFT JOIN Entrants ea ON ea.entrant_id = m.entrant_a_id "
		"LEFT JOIN Entrants eb ON eb.entrant_id = m.entrant_b_id "
		"LEFT JOIN Entrants ew ON ew.entrant_id = m.winner_entrant_id "
		"WHERE m.bracket_id = '{0}' "
		"ORDER BY m.round, m.slot".format(bracket_id))
	rows = cursor.fetchall()
	cursor.close()
	return rows


def getCommentsForBracket(bracket_id):
	cursor = conn.cursor()
	cursor.execute(
		"SELECT c.comment_id, u.username, c.matchup_id, c.body, c.created_at "
		"FROM Comments c "
		"JOIN Users u ON c.user_id = u.user_id "
		"JOIN Matchups m ON c.matchup_id = m.matchup_id "
		"WHERE m.bracket_id = '{0}' "
		"ORDER BY c.created_at DESC".format(bracket_id))
	rows = cursor.fetchall()
	cursor.close()
	return rows


@app.route('/bracket/<int:bracket_id>', methods=['GET'])
def view_bracket(bracket_id):
	bracket  = getBracketInfo(bracket_id)
	matchups = getMatchupsForBracket(bracket_id)
	comments = getCommentsForBracket(bracket_id)
	return render_template('bracket.html', bracket=bracket, matchups=matchups, comments=comments)
# end bracket view code


@app.route('/bracket/<int:bracket_id>/start_voting', methods=['POST'])
@flask_login.login_required
def start_voting(bracket_id):
	username = flask_login.current_user.id
	user_id = getUserIdFromUsername(username)

	cursor = conn.cursor()

	cursor.execute(
		"SELECT host_id, status FROM Brackets WHERE bracket_id = '{0}'".format(bracket_id)
	)
	bracket = cursor.fetchone()

	if not bracket:
		cursor.close()
		return "Bracket not found<br><a href='/browse'>Browse brackets</a>"

	if bracket[0] != user_id:
		cursor.close()
		return "Only the host can start voting<br><a href='/bracket{0}'>Back</a>".format(bracket_id)

	if bracket[1] != 'predictions_open':
		cursor.close()
		return "Predictions are not open<br><a href='/bracket{0}'>Back</a>".format(bracket_id)

	cursor.execute(
		"UPDATE Brackets SET status = 'round_1' WHERE bracket_id = '{0}'".format(bracket_id)
	)

	conn.commit()
	cursor.close()

	return redirect('/bracket/' + str(bracket_id))


@app.route('/bracket/<int:bracket_id>/close_round', methods=['POST'])
@flask_login.login_required
def close_current_round(bracket_id):
	cursor = conn.cursor()

	cursor.execute(
		"SELECT host_id, status FROM Brackets WHERE bracket_id = '{0}'".format(bracket_id)
	)
	bracket = cursor.fetchone()

	if not bracket:
		cursor.close()
		return "Bracket not found<br><a href='/browse'>Browse brackets</a>"

	user_id = getUserIdFromUsername(flask_login.current_user.id)

	if bracket[0] != user_id:
		cursor.close()
		return "Only the host can close this round<br><a href='/bracket{0}'>Back</a>".format(bracket_id)

	status = bracket[1]

	if not status.startswith('round_'):
		cursor.close()
		return "This bracket is not in a voting round<br><a href='/bracket{0}'>Back</a>".format(bracket_id)

	current_round = int(status.replace('round_', ''))

	try:
		cursor.execute(
			"CALL close_round({0}, {1})".format(bracket_id, current_round)
		)
		conn.commit()
	except Exception as e:
		conn.rollback()
		cursor.close()
		return "Close round failed: {0}<br><a href='/bracket{1}'>Back</a>".format(e, bracket_id)

	cursor.close()
	return redirect('/bracket/' + str(bracket_id)) 


@app.route('/follow/<username>')
@flask_login.login_required
def follow_user(username):
	follower_id = getUserIdFromUsername(flask_login.current_user.id)
	followed_id = getUserIdFromUsername(username)

	if follower_id == followed_id:
		return redirect('/profile/' + username)

	cursor = conn.cursor()

	try:
		cursor.execute(
			"INSERT IGNORE INTO Follows(follower_id, followed_id) "
			"VALUES ('{0}', '{1}')".format(follower_id, followed_id)
		)
		conn.commit()
	except:
		conn.rollback()

	cursor.close()
	return redirect('/profile/' + username)


@app.route('/unfollow/<username>')
@flask_login.login_required
def unfollow_user(username):
	follower_id = getUserIdFromUsername(flask_login.current_user.id)
	followed_id = getUserIdFromUsername(username)

	cursor = conn.cursor()

	cursor.execute(
		"DELETE FROM Follows "
		"WHERE follower_id='{0}' "
		"AND followed_id='{1}'".format(follower_id, followed_id)
	)

	conn.commit()
	cursor.close()

	return redirect('/profile/' + username)


# begin prediction code
@app.route('/predict', methods=['POST'])
@flask_login.login_required
def predict():
	username = flask_login.current_user.id
	user_id = getUserIdFromUsername(username)

	matchup_id = request.form.get('matchup_id')
	picked_entrant_id = request.form.get('picked_entrant_id')

	cursor = conn.cursor()
	try:
		cursor.execute(
			"INSERT INTO Predictions (user_id, matchup_id, picked_entrant_id) "
			"VALUES ('{0}', '{1}', '{2}')".format(
				user_id, matchup_id, picked_entrant_id))
		conn.commit()
	except Exception as e:
		conn.rollback()
		cursor.close()
		return "Prediction failed: {0}<br><a href='/browse'>Browse brackets</a>".format(e)

	cursor.close()
	return redirect(request.referrer or url_for('browse'))
# end prediction code


# begin vote code
@app.route('/vote', methods=['POST'])
@flask_login.login_required
def vote():
	username = flask_login.current_user.id
	user_id = getUserIdFromUsername(username)

	matchup_id = request.form.get('matchup_id')
	entrant_id = request.form.get('entrant_id')
	side = request.form.get('side')

	cursor = conn.cursor()
	try:
		cursor.execute(
			"INSERT INTO Votes (user_id, matchup_id, entrant_id) "
			"VALUES ('{0}', '{1}', '{2}')".format(
				user_id, matchup_id, entrant_id))

		if side == 'A':
			cursor.execute(
				"UPDATE Matchups SET votes_a = votes_a + 1 "
				"WHERE matchup_id = '{0}'".format(matchup_id))
		else:
			cursor.execute(
				"UPDATE Matchups SET votes_b = votes_b + 1 "
				"WHERE matchup_id = '{0}'".format(matchup_id))

		conn.commit()
	except Exception as e:
		conn.rollback()
		cursor.close()
		return "Vote failed: {0}<br><a href='/browse'>Browse brackets</a>".format(e)

	cursor.close()
	return redirect(request.referrer or url_for('browse'))
# end vote code


@app.route('/comment', methods=['POST'])
@flask_login.login_required
def comment():
	username = flask_login.current_user.id
	user_id = getUserIdFromUsername(username)

	matchup_id = request.form.get('matchup_id')
	body = request.form.get('body')

	cursor = conn.cursor()

	try:
		cursor.execute(
			"INSERT INTO Comments (user_id, matchup_id, body) "
			"VALUES ('{0}', '{1}', '{2}')".format(user_id, matchup_id, body)
		)
		conn.commit()
	except Exception as e:
		conn.rollback()
		cursor.close()
		return "Comment failed: {0}<br><a href='/browse'>Browse brackets</a>".format(e)

	cursor.close()
	return redirect(request.referrer or url_for('browse'))


# begin profile code
def getProfileInfo(username):
	cursor = conn.cursor()

	cursor.execute(
		"SELECT user_id, username, email, bio, created_at "
		"FROM Users "
		"WHERE username = '{0}'".format(username))
	user = cursor.fetchone()

	if not user:
		cursor.close()
		return None

	user_id = user[0]

	cursor.execute(
		"SELECT COALESCE(SUM(points_earned), 0), "
		"COUNT(*), "
		"COALESCE(SUM(correct_pick = TRUE), 0) "
		"FROM Predictions "
		"WHERE user_id = '{0}'".format(user_id))
	stats = cursor.fetchone()

	cursor.execute(
		"SELECT a.name, a.description, ua.earned_at "
		"FROM User_Achievements ua "
		"JOIN Achievements a "
		"ON ua.achievement_code = a.achievement_code "
		"WHERE ua.user_id = '{0}' "
		"ORDER BY ua.earned_at DESC".format(user_id))
	achievements = cursor.fetchall()

	cursor.execute(
		"SELECT bracket_id, title, status, entrant_count, created_at "
		"FROM Brackets "
		"WHERE host_id = '{0}' "
		"ORDER BY created_at DESC".format(user_id))
	hosted_brackets = cursor.fetchall()

	cursor.execute(
		"SELECT u.username "
		"FROM Follows f "
		"JOIN Users u ON f.follower_id = u.user_id "
		"WHERE f.followed_id = '{0}'".format(user_id))
	followers = cursor.fetchall()

	cursor.execute(
		"SELECT u.username "
		"FROM Follows f "
		"JOIN Users u ON f.followed_id = u.user_id "
		"WHERE f.follower_id = '{0}'".format(user_id))
	following = cursor.fetchall()

	cursor.close()

	return user, stats, achievements, hosted_brackets, followers, following


@app.route('/profile/<username>', methods=['GET'])
def profile(username):
	profile_data = getProfileInfo(username)

	if not profile_data:
		return "User not found<br><a href='/'>Home</a>"

	user, stats, achievements, hosted_brackets, followers, following = profile_data

	return render_template(
		'profile.html',
		user=user,
		stats=stats,
		achievements=achievements,
		hosted_brackets=hosted_brackets,
		followers=followers,
		following=following
	)
# end profile code


@app.route('/admin', methods=['GET', 'POST'])
@flask_login.login_required
def admin():
	if flask_login.current_user.id != 'admin':
		return "Only admin can use this page<br><a href='/'>Home</a>"

	if request.method == 'GET':
		return render_template('admin.html', sql='', rows=None, columns=None, error=None)

	sql = request.form.get('sql')

	cursor = conn.cursor()

	try:
		cursor.execute(sql)

		if cursor.description:
			columns = [col[0] for col in cursor.description]
			rows = cursor.fetchall()
			cursor.close()
			return render_template('admin.html', sql=sql, rows=rows, columns=columns, error=None)
		else:
			conn.commit()
			cursor.close()
			return render_template('admin.html', sql=sql, rows=None, columns=None, error='Query executed successfully.')

	except Exception as e:
		conn.rollback()
		cursor.close()
		return render_template('admin.html', sql=sql, rows=None, columns=None, error=e)


@app.route('/leaderboard')
def leaderboard():
	cursor = conn.cursor()

	cursor.execute("""
		SELECT
			u.username,
			COALESCE(SUM(p.points_earned), 0) AS total_points,
			RANK() OVER (
				ORDER BY COALESCE(SUM(p.points_earned), 0) DESC
			) AS ranking,
			DENSE_RANK() OVER (
				ORDER BY COALESCE(SUM(p.points_earned), 0) DESC
			) AS dense_ranking,
			PERCENT_RANK() OVER (
				ORDER BY COALESCE(SUM(p.points_earned), 0) DESC
			) AS percent_ranking
		FROM Users u
		LEFT JOIN Predictions p
			ON u.user_id = p.user_id
		GROUP BY u.user_id, u.username
		ORDER BY total_points DESC
	""")

	rows = cursor.fetchall()
	cursor.close()

	return render_template('leaderboard.html', rows=rows)


@app.route('/champion_path/<bracket_id>')
def champion_path(bracket_id):
	cursor = conn.cursor()

	cursor.execute("""
		WITH RECURSIVE champion_path AS (
			SELECT
				m.matchup_id,
				m.round,
				m.slot,
				e.name AS champion_name,
				m.winner_entrant_id
			FROM Matchups m
			JOIN Entrants e
				ON m.winner_entrant_id = e.entrant_id
			WHERE m.bracket_id = '{0}'
			  AND m.round = (
				  SELECT MAX(round)
				  FROM Matchups
				  WHERE bracket_id = '{0}'
			  )

			UNION ALL

			SELECT
				m.matchup_id,
				m.round,
				m.slot,
				e.name AS champion_name,
				m.winner_entrant_id
			FROM Matchups m
			JOIN champion_path cp
				ON m.winner_entrant_id = cp.winner_entrant_id
			JOIN Entrants e
				ON m.winner_entrant_id = e.entrant_id
			WHERE m.bracket_id = '{0}'
			  AND m.round < cp.round
		)
		SELECT matchup_id, round, slot, champion_name
		FROM champion_path
		ORDER BY round
	""".format(bracket_id))

	rows = cursor.fetchall()
	cursor.close()

	return render_template('champion_path.html', rows=rows)


# default page
@app.route('/', methods=['GET', 'POST'])
def home():
	if request.method == 'POST':
		flask_login.logout_user()
	try:
		username = flask_login.current_user.id
		return render_template('hello.html', name=username, message='welcome to VERSUS')
	except AttributeError:  # not logged in
		return render_template('hello.html', message=None)


if __name__ == "__main__":
	# this is invoked when in the shell you run
	# $ python app.py
	app.debug = True
	app.run(port=5001, debug=True)
