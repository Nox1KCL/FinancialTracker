from functools import wraps
from flask import url_for, redirect, session, flash, request
from pymongo import MongoClient
from bson.objectid import ObjectId
import re
import os

# region Decorators
def loginRequired(function):
    @wraps(function)
    def Processed(*args, **kwargs):
        if 'userId' not in session:
            return redirect(url_for('home'))
        return function(*args, **kwargs)
    return Processed

def completeProfileRequired(function):
    @wraps(function)
    def Processed(*args, **kwargs):
        connectionString = os.getenv("MONGO_URI")
        userCollection = MongoClient(connectionString).get_database('FinancialSiteBase').get_collection('Users')
        currentUser = userCollection.find_one({'_id': ObjectId(session['userId'])})

        if not currentUser or not currentUser.get('completedProfile', False):
            return redirect(url_for('completeProfile'))
        return function(*args, **kwargs)
    return Processed
# endregion

# region functions
def updateFinances(userId, transactionCollection, financesCollection):
    userTransactionsCursor = transactionCollection.find({'userId' : userId})

    totalIncome = 0
    totalExpense = 0

    for transaction in userTransactionsCursor:
        if (transaction['moneyAmount'] >= 0):
            totalIncome += transaction['moneyAmount']
        else:
            totalExpense += transaction['moneyAmount']

    balance = totalIncome + totalExpense
    financesCollection.update_one(
        {'userId': userId},
        {'$set': {
            'totalIncome': totalIncome,
            'totalExpense': totalExpense,
            'balance': balance
        }},
        upsert = True
    )


def updateProfile(userId, userCollection):
        currentUser = userCollection.find_one({'_id': ObjectId(userId)})
        # region userInfo
        newUserData = {
            'firstName': request.form['firstName'],
            'lastName': request.form['lastName'],
            'email': request.form['email'],
            'phonePrefix': request.form['phonePrefix'],
            'phoneNumber': request.form['phoneNumber'],
            'dateOfBirth': request.form['dateOfBirth'],
            'biography': request.form['biography'],
            'country': request.form['country'],
            'city': request.form['city'],
            'timezone': request.form['timezone'],
            'defaultCurrency': request.form['defaultCurrency'],
            'language': request.form['language'],
            'dateFormat': request.form['dateFormat']            
        }   
        
        userCollection.update_one(
            {'_id': ObjectId(userId)},
            {'$set': newUserData}
        )

        # endregion

        if currentUser.get('phoneNumber') and (not currentUser.get('phoneNumber').isdigit() 
                                               or len(currentUser.get('phoneNumber')) != 9):
            flash('Invalid phone number. Please enter exactly 9 digits', 'danger')
            return


def emailCheck(email, userCollection):
    emailRegex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    isValidFormat = re.match(emailRegex, email) 
    allowedAdresses = (
        '@gmail.com',
        '@outlook.com',
        '@hotmail.com',
        '@yahoo.com',
        '@icloud.com',
        '@ukr.net',
        '@i.ua',
        '@meta.ua',
        '@proton.me'
    )
    isRightAdress= email.endswith(allowedAdresses)

    if not isValidFormat or not isRightAdress:
        flash(f'Invalid email format or adress: "{email}"', 'danger')
        return False
        
    if userCollection.find_one({'email': email}):
        flash(f'Email {email} already exists', 'danger')
        return False
    
    return True

# endregion