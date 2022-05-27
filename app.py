from flask import Flask, render_template, url_for, flash, redirect, request, session, logging
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from datetime import datetime
from wtforms import Form, StringField, TextAreaField, PasswordField, validators
from passlib.hash import sha256_crypt
import os
from werkzeug.utils import secure_filename
from functools import wraps
from api import insight_weather
import sqlite3
import requests

##########################  CONFIG  ####################################
#API
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite3'
db = SQLAlchemy(app)
migrate = Migrate(app, db)
migrate.init_app(app, db)

app.secret_key = 'perseverancekey'

app.config['UPLOAD_FOLDER'] = '.\\static\\profile_pics'
ALLOWED_EXTENSIONS = set(['png', 'jpg', 'jpeg', 'JPG', 'PNG'])


############################    MODELS  ##################################

# Likes association table (associates between users and likes with to columns)
likes = db.Table('likes',
                 db.Column('user_id', db.Integer, db.ForeignKey('user.id')),
                 db.Column('post_id', db.Integer, db.ForeignKey('post.id'))
                 )


# Likes association table (associates between users and likes with to columns)
followers = db.Table('follows',
                     db.Column('follower_id', db.Integer,
                               db.ForeignKey('user.id'), nullable=True),
                     db.Column('followed_id', db.Integer,
                               db.ForeignKey('user.id'), nullable=True)
                     )


# User model
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(25), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    image_file = db.Column(db.String(20), default='default.jpg')
    password = db.Column(db.String(64), nullable=False)
    verified = db.Column(db.Integer, default=0, nullable=True)
  
    likes = db.relationship('Post', secondary=likes,
                            backref=db.backref('likes', lazy='dynamic'), lazy='dynamic')
    followed = db.relationship('User', secondary=followers,
                               primaryjoin=(followers.c.follower_id == id),
                               secondaryjoin=(followers.c.followed_id == id),
                               backref=db.backref('followers', lazy='dynamic'), lazy='dynamic')  
    account_type = db.Column(db.String(20))
    access_getway = db.Column(db.String(20))
    image_cover = db.Column(db.String(20), default='default-cover.png')
    posts = db.relationship('Post', backref='author', lazy=True)
    # Defines how a user object will be printed in the shell
    def __repr__(self):
        return f"User ('{self.username}', '{self.email}', '{self.id}')"


# Post model
class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date_posted = db.Column(db.DateTime, nullable=False,
                            default=datetime.utcnow)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    retweet = db.Column(db.Integer, default=None, nullable=True, unique=False)
    comment = db.Column(db.Integer, default=None, nullable=True, unique=False)
    image_url = db.Column(db.Integer, default=None, nullable=True, unique=False)
    # Defines how a post object will be printed in the shell
    def __repr__(self):
        return f"Post ('{self.id}', '{self.date_posted}', '{self.image_url}')"


##################################  UTILS #####################################

# Check if user logged in
def is_logged_in(f):
    @wraps(f)
    def wrap(*args, **kwargs):
        if 'logged_in' in session:
            return f(*args, **kwargs)
        else:
            flash('Unauthorized, Please login', 'danger')
            return redirect(url_for('login'))
    return wrap


# Returns current user
def current_user():
    if len(session) > 0:
        return User.query.filter_by(username=session['username']).first()
    else:
        return None


############################    ROUTES  #####################################

# Home route (default)
@app.route('/')
def home():
    trending = []
    con = sqlite3.connect("db.sqlite3")
    cur = con.cursor()
    cur.execute("SELECT COUNT('user_id'), content ,p.user_id ,username from likes, post p,user u WHERE post_id = p.id and p.user_id = u.id GROUP BY content ORDER BY COUNT('user_id') DESC LIMIT 6")
    row = cur.fetchall()
    con.commit()
    con.close()
    if 'logged_in' in session:
        posts = Post.query.filter_by(comment=None).all()
        follow_suggestions = User.query.all()[0:7]

        # Remove current user from follow suggestions
        if current_user():  # If there is a user in the session
            if current_user() in follow_suggestions:  # If the current user is in the user's follow suggestions
                follow_suggestions.remove(current_user())
        #profile_pic = url_for('static', filename='profile_pics/' + postes)        
        #print(posts)
        return render_template('home.html', season={}, posts=posts, user=current_user(), Post_model=Post, likes=likes, follow_suggestions=follow_suggestions, User=User, trending=row, showTrending = True)
    else:
        return render_template("index.html")

# Home route (following)
@app.route('/home_following')
@is_logged_in
def home_following():
    posts = []
    follow_suggestions = User.query.all()[0:6]

    follows = current_user().followed.all()

    for follow in follows:  # Get all posts by folled accounts
        user_posts = Post.query.filter_by(author=follow)
        posts += user_posts

    posts.sort(key=lambda r: r.date_posted)  # Sorts posts by date

    # Remove current user from follow suggestions
    if current_user():  # If there is a user in the session
        if current_user() in follow_suggestions:  # If the current user is in the user's follow suggestions
            follow_suggestions.remove(current_user())

    return render_template('home.html', posts=posts, user=current_user(), Post_model=Post, likes=likes, follow_suggestions=follow_suggestions, User=User, showTrending = False)


# Single post route
@app.route('/post/<int:id>')
def post(id):
    post = Post.query.filter_by(id=id).first()
    return render_template('post.html', id=id, post=post, Post_model=Post, user=current_user())


# Register form class
class RegisterForm(Form):
    username = StringField('Username', [validators.Length(min=1, max=25)])
    email = StringField('Email', [validators.Length(min=6, max=120)])
    password = PasswordField('Password', [
        validators.DataRequired(),
        validators.EqualTo('confirm', message='Passwords do not match')
    ])
    confirm = PasswordField('Confirm Password')


# Register route
@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegisterForm(request.form)
    if request.method == 'POST' and form.validate():

        # Get form data
        username = form.username.data
        email = form.email.data.lower()
        password = sha256_crypt.encrypt(str(form.password.data))
        type1 = request.form['type']
        #print(type1)       
        # Make user object with form data
        user = User(username=username, email=email, password=password, account_type=type1)

        # Add user object to session
        db.session.add(user)

        # Commit session to db
        db.session.commit()

        #flash('You are now registered and can log in', 'success')

        return redirect(url_for('login'))

    return render_template('register.html', form=form)


# User login
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Get form fields
        email = request.form['email'].lower()
        password_candidate = request.form['password']

        # Get user by email
        user = User.query.filter_by(email=email).first()

        # If there is a user with the email
        if user != None:
            # Get stored hash
            password = user.password

            # If passwords match
            if sha256_crypt.verify(password_candidate, password):
                # Passed
                session['logged_in'] = True
                session['username'] = user.username
                session['user_id'] = user.id
                session['type'] = user.account_type
                session['cover_image'] = user.image_cover
                session['image_file'] = user.image_file
                #print(session['type'])
                app.logger.info(f'{user.username} LOGGED IN SUCCESSFULLY')
                flash('You are now logged in', 'success')
                return redirect(url_for('home'))

            # If passwords don't match
            else:
                error = 'Invalid password'
                return render_template('login.html', error=error)

        # No user with the email
        else:
            error = 'Email not found'
            return render_template('login.html', error=error)

    # GET Request
    return render_template('login.html')


# Logout
@app.route('/logout')
@is_logged_in
def logout():
    session.clear()
    #flash('You are now logged out', 'success')
    return redirect(url_for('login'))


# Profile route
@app.route('/profile')
@is_logged_in
def profile():
    if 'logged_in' in session:
        cover_pic = url_for('static', filename=f'profile_pics/{current_user().image_cover}')
        profile_pic = url_for('static', filename=f'profile_pics/{current_user().image_file}')
        print(profile_pic)
        if session['type'] == 'Regular':
            return render_template('profiles/regular.html', profile_pic=profile_pic, cover_pic=cover_pic, username=current_user().username, modify=True)
        elif  session['type'] == 'Creative':
            return render_template('profiles/creative.html', profile_pic=profile_pic, cover_pic=cover_pic, username=current_user().username, modify=True)
        elif  session['type'] == 'Business':
            return render_template('profiles/business.html', profile_pic=profile_pic, cover_pic=cover_pic, username=current_user().username, modify=True)

    else:
        return render_template("404.html", code=404)

@app.route('/profile/<id>')
def otherProfile(id):
    con = sqlite3.connect("db.sqlite3")
    cur = con.cursor()
    cur.execute(f"SELECT * FROM user WHERE id={id}")
    row = cur.fetchall()
    username = row[0][1]
    image = row[0][3]
    posts = Post.query.filter_by(user_id=id).all()
    print(posts)
    con.commit()
    con.close()
    #cover_pic = url_for('static', filename=f'profile_pics/{current_user().image_cover}')
    profile_pic = url_for('static', filename=f'profile_pics/{current_user().image_file}')

    if session['type'] == 'Regular':
            return render_template('profiles/regular.html', profile_pic=profile_pic,posts=posts,user=current_user(), Post_model=Post,username=current_user().username, modify=True)
    elif  session['type'] == 'Creative':
            return render_template('profiles/creative.html', profile_pic=profile_pic,posts=posts,user=current_user(), Post_model=Post,username=current_user().username, modify=True)
    elif  session['type'] == 'Business':
            return render_template('profiles/business.html', profile_pic=profile_pic,posts=posts,user=current_user(), Post_model=Post, username=current_user().username, modify=True)



# Post form class
class PostForm(Form):
    content = TextAreaField('Content', [validators.Length(min=1, max=280)])

# New Post
@app.route('/new_post/', methods=['GET', 'POST'])
@is_logged_in
def new_post():

    form = PostForm(request.form)
    if request.method == 'POST' and form.validate():

        # Get form content
        content = ''
        imgurl = ''
        content = form.content.data
        file1 = request.files['file']
        # If empty file

        if file1.filename == '':

            flash('No file selected', 'danger')
            return redirect(url_for('home'))

        # If there is a file and it is allowed
        if file1 and allowed_file(file1.filename):

            filename = secure_filename(file1.filename)

            current_user().image_url = filename
            db.session.commit()

            file1.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            #print(file1.filename)
    

        # Make post object
            post = Post(content=content, author=current_user(), image_url="static/profile_pics/" + file1.filename)
            
        # Add post to db session
            db.session.add(post)
            

        # Commit session to db
            db.session.commit()
            

            flash('Your new post has been created!  😊', 'success')
            return redirect(url_for('home'))

    return render_template('new_post.html', form=form, title='New post')


# Like post
@app.route('/like/<id>')
@is_logged_in
def like_post(id):

    post = Post.query.filter_by(id=id).first()

    # If the requested post does not exist
    if post is None:
        flash(f"Post '{id}' not found", 'warning')
        return redirect(url_for('home'))

    # If the user has already liked the post
    if current_user() in post.likes.all():
        post.likes.remove(current_user())
        db.session.commit()
        return redirect(url_for('home', _anchor=id))
    # If the user has not liked the post yet
    else:
        post.likes.append(current_user())
        db.session.commit()
        return redirect(url_for('home', _anchor=id))


# Split filename into file extension
def allowed_file(filename):
    return '.' in filename and \
        filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


# Update picture
@app.route('/update_photo', methods=['GET', 'POST'])
@is_logged_in
def update_photo():

    if request.method == 'POST':

        # No file selected
        if 'file' not in request.files:

            flash('No file selected', 'danger')
            return redirect(url_for('update_photo'))

        file = request.files['file']
        # If empty file
        if file.filename == '':

            flash('No file selected', 'danger')
            return redirect(url_for('update_photo'))

        # If there is a file and it is allowed
        if file and allowed_file(file.filename):

            filename = secure_filename(file.filename)

            current_user().image_file = filename
            user = User(content=content, author=current_user(), image_url="static/profile_pics/" + file.filename)

        # Add post to db session
            db.session.add(user)
            db.session.commit()

            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

            flash(f'Succesfully changed profile picture to {filename}', 'success')
            return redirect(url_for('profile'))

    return render_template('update_photo.html', user=current_user())



# Search route
@app.route('/search', methods=['GET', 'POST'])
def search():
    if request.method == 'POST':

        # Get query from form
        query = request.form['search']

        # Search and save posts
        posts = Post.query.filter(
            Post.content.like('%' + query + '%'))

        return render_template('results.html', posts=posts, Post_model=Post, user=current_user(), query=query)


# Follow route
@app.route('/follow/<id>')
@is_logged_in
def follow(id):

    # Get current user
    user_following = current_user()
    # Find user being followed by id
    user_followed = User.query.filter_by(id=id).first()

    if user_following == user_followed:

        flash('You cant follow yourself -_-', 'danger')
        return redirect(url_for('home'))

    else:
        # Follow user
        user_following.followed.append(user_followed)

        # Commit to db
        db.session.commit()

        flash(f'Followed {user_followed.username}', 'success')
        return redirect(url_for('home'))


# Unfollow route
@app.route('/unfollow/<id>')
@is_logged_in
def unfollow(id):
    # Get current user
    user_unfollowing = current_user()
    # Get user being unfollowed by id
    user_unfollowed = User.query.filter_by(id=id).first()

    if user_unfollowing == user_unfollowed:

        flash('You cant unfollow yourself -_-', 'danger')
        return redirect(url_for('home'))

    else:
        # Unfollow
        user_unfollowing.followed.remove(user_unfollowed)

        # Commit to db
        db.session.commit()

        flash(f'Unfollowed {user_unfollowed.username}', 'warning')
        return redirect(url_for('home'))


# Retweet route
@app.route('/retweet/<id>')
@is_logged_in
def retweet(id):
    re_post = Post.query.filter_by(id=id).first()

    if re_post.retweet != None:
        flash("You can't retweet a retweeted tweet :(", 'danger')
        return redirect(url_for('home'))

    if Post.query.filter_by(user_id=current_user().id).filter_by(retweet=id).all():
        rm_post = Post.query.filter_by(
            user_id=current_user().id).filter_by(retweet=id).first()
        db.session.delete(rm_post)
        db.session.commit()

        flash('Unretweeted successfully', 'warning')
        return redirect(url_for('home'))

    post = Post(content='', user_id=current_user().id, retweet=id)
    db.session.add(post)
    db.session.commit()

    flash('Retweeted successfully', 'success')
    return redirect(url_for('home'))


# New Comment
@app.route('/new_comment/<post_id>', methods=['GET', 'POST'])
@is_logged_in
def new_comment(post_id):

    # Commented post
    commented_post = Post.query.filter_by(id=post_id).first()

    form = PostForm(request.form)
    if request.method == 'POST' and form.validate():

        # Get form content
        content = f'@{commented_post.author.username}  ' + form.content.data

        # Make comment object
        comment = Post(content=content, author=current_user(), comment=post_id)

        # Add comment to db session
        db.session.add(comment)

        # Commit session to db
        db.session.commit()

        flash(
            f"You have replied to {commented_post.author.username}", 'success')
        return redirect(url_for('home'))

    return render_template('new_post.html', form=form, title=f"Comment to @{commented_post.author.username}")


@app.errorhandler(404)
def error404(error):
    return render_template('404.html'), 404


if __name__ == '__main__':
    app.run(debug=True)
