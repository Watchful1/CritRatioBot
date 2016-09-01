#!/usr/bin/python3

import praw
import OAuth2Util
import os
import logging.handlers
import sqlite3
from datetime import datetime
import re

### Config ###
LOG_FOLDER_NAME = "logs"
SUBREDDIT = "SeriousShortStories"

### Logging setup ###
LOG_LEVEL = logging.DEBUG
if not os.path.exists(LOG_FOLDER_NAME):
    os.makedirs(LOG_FOLDER_NAME)
LOG_FILENAME = LOG_FOLDER_NAME+"/"+"bot.log"
LOG_FILE_BACKUPCOUNT = 5
LOG_FILE_MAXSIZE = 1024 * 256

log = logging.getLogger("bot")
log.setLevel(LOG_LEVEL)
log_formatter = logging.Formatter('%(levelname)s: %(message)s')
log_stderrHandler = logging.StreamHandler()
log_stderrHandler.setFormatter(log_formatter)
log.addHandler(log_stderrHandler)
if LOG_FILENAME is not None:
	log_fileHandler = logging.handlers.RotatingFileHandler(LOG_FILENAME, maxBytes=LOG_FILE_MAXSIZE, backupCount=LOG_FILE_BACKUPCOUNT)
	log_formatter_file = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
	log_fileHandler.setFormatter(log_formatter_file)
	log.addHandler(log_fileHandler)


### Main ###
log.debug("Connecting to reddit")

r = praw.Reddit(user_agent="CritRatio (by /u/Watchful1)", log_request=0)
o = OAuth2Util.OAuth2Util(r)
o.refresh(force=True)

dbConn = sqlite3.connect("database.db")

c = dbConn.cursor()
c.execute('''
	CREATE TABLE IF NOT EXISTS users (
		ID INTEGER PRIMARY KEY AUTOINCREMENT,
		User VARCHAR(80) NOT NULL,
		CommentedWords INT NOT NULL,
		PostedWords INT NOT NULL,
		UNIQUE (User)
	)
''')
c.execute('''
	CREATE TABLE IF NOT EXISTS lastRun (
		ID INTEGER PRIMARY KEY,
		LastRun TIMESTAMP
	)
''')
dbConn.commit()

loopStartTime = datetime.utcnow()

lastRunResult = c.execute('''
	SELECT LastRun
	FROM lastRun
	WHERE ID = 1
''').fetchone()

lastRun = None
if lastRunResult:
	lastRun = datetime.strptime(lastRunResult[0], "%Y-%m-%d %H:%M:%S")

for comment in r.get_subreddit(SUBREDDIT).get_comments(limit=1000):
	if lastRun is not None and datetime.utcfromtimestamp(comment.created_utc) < lastRun: break

	if not comment.is_root:
		log.debug("Skipping comment by /u/"+str(comment.author)+", not root")
		continue

	submission = comment.submission
	if str(submission.author) == str(comment.author):
		log.debug("Skipping comment by /u/"+str(comment.author)+", posted by thread author")
		continue

	title = submission.title
	numbers = re.findall('(\d[\d\,\.]{2,})', title)

	if len(numbers) == 0:
		log.debug("Skipping comment by /u/"+str(comment.author)+", not in a story thread")
		continue

	wordCount = int(numbers[0].replace('.', '').replace(',', ''))

	isSecondComment = False
	for submissionComment in submission.comments:
		if submissionComment == comment: continue
		if not submissionComment.is_root: continue

		if str(submissionComment.author) == str(comment.author):
			isSecondComment = True
			break

	if isSecondComment:
		log.debug("Skipping comment by /u/"+str(comment.author)+", second comment by commenter in thread")
		continue

	previousWordCount = c.execute('''
		SELECT CommentedWords
		FROM users
		WHERE User = ?
	''', (str(comment.author).lower(),)).fetchone()

	log.info("Found comment by /u/" + str(comment.author) + ", story word count: "+str(wordCount)+" previous word count: "+(str(previousWordCount[0] if previousWordCount else "0")))

	if previousWordCount:
		c.execute('''
			UPDATE users
			SET CommentedWords = ?
			WHERE User = ?
		''', (previousWordCount[0]+wordCount, str(comment.author).lower()))
	else:
		c.execute('''
			INSERT INTO users
			(User, CommentedWords, PostedWords)
			VALUES (?, ?, 0)
		''', (str(comment.author).lower(), wordCount))

for submission in r.get_subreddit(SUBREDDIT).get_new(limit=1000):
	if lastRun is not None and datetime.utcfromtimestamp(submission.created_utc) < lastRun: break

	numbers = re.findall('(\d[\d\,\.]{2,})', submission.title)

	if len(numbers) == 0:
		log.debug("Skipping thread by /u/"+str(submission.author)+", not a story thread")
		continue

	wordCount = int(numbers[0].replace('.', '').replace(',', ''))

	previousWordCount = c.execute('''
		SELECT PostedWords
		FROM users
		WHERE User = ?
	''', (str(submission.author).lower(),)).fetchone()

	log.info("Found thread by /u/" + str(submission.author) + ", story word count: "+str(wordCount)+" previous word count: "+(str(previousWordCount[0] if previousWordCount else "0")))

	if previousWordCount:
		c.execute('''
			UPDATE users
			SET PostedWords = ?
			WHERE User = ?
		''', (previousWordCount[0]+wordCount, str(submission.author).lower()))
	else:
		c.execute('''
			INSERT INTO users
			(User, CommentedWords, PostedWords)
			VALUES (?, 0, ?)
		''', (str(submission.author).lower(), wordCount))


if lastRun:
	c.execute('''
		UPDATE lastRun
		SET LastRun = ?
		WHERE ID = 0
	''', (loopStartTime.strftime("%Y-%m-%d %H:%M:%S"),))
else:
	c.execute('''
		INSERT INTO lastRun
		(ID, LastRun)
		VALUES (1, ?)
	''', (loopStartTime.strftime("%Y-%m-%d %H:%M:%S"),))

dbConn.commit()
dbConn.close()