# region Imports
from flask import Flask, request, render_template, url_for, redirect, session, flash
from pymongo import MongoClient
from bson.objectid import ObjectId
from flask_mail import Mail, Message
from itsdangerous import URLSafeTimedSerializer, SignatureExpired
import utils

import os
from dotenv import load_dotenv

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
import re

from werkzeug.security import generate_password_hash, check_password_hash
# endregion


app = Flask(__name__)
connectionString = os.getenv("MONGO_URI")
client = MongoClient(connectionString)
db = client['FinancialSiteBase']
transactionCollection = db['Transactions']
userCollection = db['Users']
financesCollection = db['Finances']
app.secret_key = os.getenv("SECRET_KEY")

app.config['MAIL_SERVER'] = 'smtp.gmail.com'
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = 'korshunov.maks09@gmail.com'
app.config['MAIL_PASSWORD'] = os.getenv("MAIL_PASS")
app.config['MAIL_DEFAULT_SENDER'] = 'korshunov.maks09@gmail.com'
mail = Mail(app)
s = URLSafeTimedSerializer(app.secret_key)


# region Home
@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        # region Register
        if request.form.get('action') == 'register':
            username = request.form['username']
            email = request.form['email']
            password = request.form['password']
            confirmPassword = request.form['confirmPassword']

            # region check email and username
            emailChecked = utils.emailCheck(email, userCollection)
            if not emailChecked:
                return render_template('home.html', openModal='register')
            
            if userCollection.find_one({'username': username}):
                flash(f'Username {username} already exists', 'danger')
                return render_template('home.html', openModal='register')
            # endregion
            
            # region check password
            if password != confirmPassword:
                flash('Passwords do not match', 'danger')
                return render_template('home.html', openModal='register')
            hashed_password = generate_password_hash(password)
            # endregion

            userCollectionName = username
            userCollectionName = {
                'username': username,
                'email': email,
                'password': hashed_password,
                'completedProfile': False
            }

            userCollection.insert_one(userCollectionName)
            return redirect(url_for('home'))
        # endregion
        
        # region Login
        elif request.form.get('action') == 'login':
            username = request.form['username']
            password = request.form['password']

            user = userCollection.find_one({'username': username})
            if user and check_password_hash(user['password'], password):
                session['userId'] = str(user['_id'])
                session['username'] = user['username']

                if not user.get('completedProfile', False):
                    return redirect(url_for('completeProfile'))
                else:
                    return redirect(url_for('transactions'))
            else:
                flash('Invalid username or password', 'danger')
                return render_template('home.html', openModal='login')   
        # endregion         
    else:
        return render_template('home.html')
# endregion


# region Transactions
@app.route('/transactions', methods=['GET', 'POST'])
@utils.loginRequired
@utils.completeProfileRequired
def transactions():
    currentUserId = session['userId']
    username = session['username']
    currentUser = userCollection.find_one({'username': username})

    # region Add new transaction
    if request.method == 'POST':
        transactionType = request.form['transactionType']
        moneyAmount = abs(float(request.form['amount']))
        description = request.form['description']
        category = request.form['category']
        date = request.form.get('date')
        time = request.form.get('time')

        userTimezone = currentUser.get('timezone')
        try:
            userTimezone = ZoneInfo(userTimezone) if userTimezone else timezone.utc
        except ZoneInfoNotFoundError:
            userTimezone = timezone.utc


        if transactionType == 'expense' and moneyAmount > 0:
            moneyAmount = -moneyAmount
        
        newTransaction = {
            'transactionType': transactionType,
            'description': description,
            'moneyAmount': moneyAmount,
            'category': category,
            'date': date,
            'time': time,
            'userId': currentUserId
        }

        transactionCollection.insert_one(newTransaction)
        utils.updateFinances(currentUserId, transactionCollection, financesCollection)

        return redirect(url_for('transactions'))
    # endregion

    # region Display transactions/Summary financial info
    else:
        userTransactionsCursor = transactionCollection.find({'userId' : currentUserId})
        transactionsList = []

        userTimezone = currentUser.get('timezone')
        try:
            userTimezone = ZoneInfo(userTimezone) if userTimezone else timezone.utc
        except ZoneInfoNotFoundError:
            userTimezone = timezone.utc

        #transactionsList = list(userTransactionsCursor)
        financialInfo = financesCollection.find_one({'userId': currentUserId}) or {}

        # region Filtering
        textFilter = request.args.get('textQuery', '')
        categoryFilter = request.args.get('categoryQuery', '')
        dateFilter = request.args.get('dateQuery', '')
        typeFilter = request.args.get('typeQuery', '')
        periodFilter = request.args.get('periodFilter', 'all')

        filterQuery = {'userId': currentUserId}
        
        today = datetime.now()
        if periodFilter == 'today':
            startDate = today.replace(hour=0, minute=0, second=0, microsecond=0)
            filterQuery['date'] = {'$gte': startDate.strftime(currentUser.get('dateFormat', '%Y-%m-%d'))}
        elif periodFilter == 'week':
            startDate = today - timedelta(days=today.weekday())
            filterQuery['date'] = {'$gte': startDate.strftime(currentUser.get('dateFormat', '%Y-%m-%d'))}
        elif periodFilter == 'month':
            startDate = today.replace(day=1)
            filterQuery['date'] = {'$gte': startDate.strftime(currentUser.get('dateFormat', '%Y-%m-%d'))}
        elif periodFilter == 'year':
            startDate = today.replace(month=1, day=1)
            filterQuery['date'] = {'$gte': startDate.strftime(currentUser.get('dateFormat', '%Y-%m-%d'))}

        if textFilter:
            filterQuery['description'] = {'$regex': textFilter, '$options': 'i'}
        if categoryFilter:
            filterQuery['category'] = categoryFilter
        if dateFilter:
            filterQuery['date'] = dateFilter
        if typeFilter :
            filterQuery['transactionType'] = typeFilter

        userTransactionsCursor = transactionCollection.find(filterQuery)
        transactionsList = list(userTransactionsCursor)

        totalIncome = sum(t['moneyAmount'] for t in transactionsList if t['moneyAmount'] > 0)
        totalExpense = sum(t['moneyAmount'] for t in transactionsList if t['moneyAmount'] < 0)
        balance = totalIncome + totalExpense
        # Подумати куда кинути цей блок
        
        now = datetime.now()
        currentData = now.strftime('%Y-%m-%d')
        currentTime = now.strftime('%H:%M')
        # endregion

    # endregion 

        return render_template('Transactions.html', transactions=transactionsList,
                               currentUser = currentUser, 
                               textFilter = textFilter,
                               categoryFilter = categoryFilter,
                               dateFilter = dateFilter,
                               typeFilter = typeFilter,
                               activePeriod = periodFilter,
                               totalIncome=financialInfo.get('totalIncome', 0), 
                               totalExpense=financialInfo.get('totalExpense', 0), 
                               balance=financialInfo.get('balance', 0))
    
# endregion


# region Analytics
@app.route('/analytics')
@utils.loginRequired
@utils.completeProfileRequired
def analytics():
    currentUserId = session['userId']
    pipeline = [
        {'$match': {'userId': currentUserId, 'transactionType': 'expense'}},
        {'$group': {'_id': '$category', 'totalAmount': {'$sum': '$moneyAmount'}}},
        {'$sort': {'totalAmount': 1}}
    ]
    expenseByCategory = list(transactionCollection.aggregate(pipeline))
    
    labels = [item['_id'] for item in expenseByCategory]
    data = [abs(item['totalAmount']) for item in expenseByCategory]

    return render_template('Analytics.html', labels=labels, data=data)
# endregion


# region Complete Profile
@app.route('/complete-profile', methods=['GET', 'POST'])
@utils.loginRequired
def completeProfile():
    if request.method == 'POST':
        firstName = request.form['firstName']
        lastName = request.form['lastName']
        timeZoneInput = request.form['timezone']
        
        try:
            userTimezone = ZoneInfo(timeZoneInput)
        except ZoneInfoNotFoundError:
            flash(f'Invalid timezone selected: "{timeZoneInput}", Try format like "Europe/Kyiv"', 'danger')
            return redirect(url_for('completeProfile'))

        userCollection.update_one(
            {'_id': ObjectId(session['userId'])},
            {'$set': {
                'firstName': firstName,
                'lastName': lastName,
                'timezone': str(userTimezone),
                'completedProfile': True
            }}
        )
        return redirect(url_for('transactions'))
    else:
        return render_template('CompleteProfile.html')
# endregion


# region Delete Transaction
@app.route('/delete-transaction/<transactionId>', methods=['POST'])
@utils.loginRequired
def deleteTransaction(transactionId):
    transactionToDelete = transactionCollection.find_one({
        '_id': ObjectId(transactionId),
        'userId': session['userId']
    })

    if transactionToDelete:
        transactionCollection.delete_one({'_id': ObjectId(transactionId)})
        utils.updateFinances(session['userId'])

        flash('Transaction deleted successfully', 'success')
    else:
        flash('Transaction not found or you do not have permission to delete it', 'danger')

    return redirect(url_for('transactions'))
# endregion


# region Forgot Password Reset
@app.route('/forgot-password', methods=['GET', 'POST'])
def passwordReset():
    if request.method == 'POST':
        email = request.form['email']
        user = userCollection.find_one({'email': email})
            
        if user:
            token = s.dumps(email, salt='email-confirm')
            resetLink = url_for('resetPassword', token=token, _external=True)

            msg = Message('Password Reset Request', recipients=[email])
            msg.body = f'Click the link to reset your password: {resetLink}'
            mail.send(msg)

            flash('Password updated successfully', 'success')
            return redirect(url_for('home'))
        else:
            flash('Email not found', 'danger')
            return render_template('ForgotPassword.html', openModal='forgotPassword')
        
    else:
        return render_template('ForgotPassword.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def resetPassword(token):
    try:
        email = s.loads(token, salt='email-confirm', max_age=3600)
    except SignatureExpired:
        flash('The password reset link has expired.', 'danger')
        return redirect(url_for('passwordReset', openModal='forgotPassword'))
    except:
        flash('Invalid password reset link.', 'danger')
        return redirect(url_for('passwordReset', openModal='forgotPassword'))

    if request.method == 'POST':
        newPassword = request.form['newPassword']
        confirmNewPassword = request.form['confirmNewPassword']

        if newPassword != confirmNewPassword:
            flash('Passwords do not match', 'danger')
            return render_template('ResetPassword.html', token=token)

        hashed_password = generate_password_hash(newPassword)
        userCollection.update_one(
            {'email': email},
            {'$set': {'password': hashed_password}}
        )

        flash('Password updated successfully', 'info')
        return redirect(url_for('home'))
    else:
        return render_template('ResetPassword.html', token=token)
# endregion


# region About User
@utils.loginRequired
@utils.completeProfileRequired
@app.route('/about-user', methods=['GET', 'POST'])
def aboutUser():
    currentUserId = session['userId']
    username = session['username']
    currentUser = userCollection.find_one({'username': username})

    if request.method == 'POST':
        utils.updateProfile(currentUserId, userCollection)
        flash('Profile updated successfuly!', 'success')
        return redirect(url_for('aboutUser'))
    
    else:
        return render_template('AboutUser.html', currentUser = currentUser)    
# endregion


# region Logout
@app.route('/logout')
@utils.loginRequired
def logout():
    session.pop('userId', None)
    session.pop('username', None)
    return redirect(url_for('home'))
# endregion