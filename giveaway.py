class GiveawaySteps:
    def __init__(self):
        self.rejected = 0
        self.request_received = 1
        self.approved = 2
        self.received_gc = 3
        self.post_made = 4
        self.staff_notified_about_start = 5
        self.finished = 6
        self.winners_pending = 7
        self.winners_confirmed = 8
        self.staff_notified_about_end = 9
        self.all_prizes_claimed = 10



def Giveaway():
    requests = Check_For_Giveaway_Request()

    if requests:
        for request in requests:
            Move_Giveaway_Request_To_Main_Database(request)

    sql = "SELECT DATE_FORMAT(`end_date`, '%m/%d/%y'), `giveaway_id`, `post`, `prizes`, `site_name`, DATE_FORMAT(`start_date`, '%m/%d/%y'), `username` FROM `giveaway` WHERE `step`=1 LIMIT 1;"
    request = Run_Mysql_Query(sql, None, DB_NAME)

    if request:
        db_id, modmail_id = Send_Initial_Modmail(request[0])
        last_checked_msg = subreddit.modmail(modmail_id).messages[0].id

        sql = "UPDATE `giveaway` SET `modmail_id`=%s, `last_checked_modmail_msg`=%s, `step`=2  WHERE `giveaway_id`=%s; "
        values = [modmail_id, last_checked_msg, db_id]
        Run_Mysql_Query(sql, values, DB_NAME)

    Check_Modmail_For_Commands()



def Giveaway_Hourly():
    for submission in subreddit.hot(limit=2):
        if submission.author in mods and submission.link_flair_text == "GIVEAWAY" and "requirements" in submission.selftext.lower():
            Update_Automod_New_Account_On_Giveaway_Removal(post_id=submission.id)
            Update_Giveaway_Request_With_Post_Id(giveaway_id=submission.id)



def Get_Already_Selected_Winners(SPREADSHEET_ID):
    selected_winners = []

    winners_already_selected = Get_Spreadsheet_Values("Winner_Info", SPREADSHEET_ID)

    for winner in winners_already_selected:
        if len(winner) > 1   and   winner[1] != "":
            selected_winners.append(winner)

    return selected_winners



# Takes the modmail message, finds the appropriate hyperlink, and then strips it apart to get the post_id
# Returns the post_id
def Get_Post_ID(modmail_msg):
    post_id = None
    search_phrase = None

    # Check if it's in redd.it or reddit.com format
    if "redd.it" in modmail_msg:
        search_phrase = "redd.it/"
    elif "reddit.com" in modmail_msg:
        search_phrase = "/comments/"

    if search_phrase:
        start_index = modmail_msg.index(search_phrase) + len(search_phrase)

        if "/" in modmail_msg[start_index:]:
            end_index = start_index + modmail_msg[start_index:].index("/")
        else:
            end_index = len(modmail_msg)

        post_id = modmail_msg[start_index:end_index]

    return post_id



def Get_Giveaway_Spreadsheet_Variables(SPREADSHEET_ID):
    RANGE_VARIABLES = "Bot_Variables"

    variables = Get_Spreadsheet_Values(RANGE_VARIABLES, SPREADSHEET_ID)

    current_giveaway_link = variables[0][0]
    num_posts_required = int(variables[4][0])
    num_prizes_desired = int(variables[2][0])
    num_prizes_selected = int(variables[3][0])
    previous_giveaway_link = variables[1][0]
    previous_winners = []

    return current_giveaway_link, previous_giveaway_link, num_prizes_desired, num_prizes_selected, num_posts_required, previous_winners



def Giveaway_Winner_Spreadsheet_Handler():
    RANGE_STATUS = "Bot_Status"
    SPREADSHEET_ID = giveaway.spreadsheet_id

    status =    {
                "done": "Done",
                "run": "Running",
                "wait": "Waiting (180 seconds)\nPlease ensure # Prize and Post Link are correct"
                }


    current_giveaway_link, previous_giveaway_link, num_prizes_desired, num_prizes_selected, num_posts_required, previous_winners = Get_Giveaway_Spreadsheet_Variables(SPREADSHEET_ID)


    if num_prizes_desired > num_prizes_selected   or   current_giveaway_link != previous_giveaway_link:
        Update_Spreadsheet_Values(RANGE_STATUS, SPREADSHEET_ID, [[status["wait"]]])

        print("Giveaway Picker Started - Waiting 3 minutes")
        three_minutes = 60 * 3
        #time.sleep(three_minutes)

        Update_Spreadsheet_Values(RANGE_STATUS, SPREADSHEET_ID, [[status["run"]]])
        Update_Spreadsheet_Values(RANGE_STATUS, SPREADSHEET_ID, [[status["run"]]])



        current_giveaway_link, previous_giveaway_link, num_prizes_desired, num_prizes_selected, num_posts_required, previous_winners = Get_Giveaway_Spreadsheet_Variables(SPREADSHEET_ID)


        if current_giveaway_link == previous_giveaway_link and num_prizes_desired > num_prizes_selected:
            previous_winners = Get_Already_Selected_Winners(SPREADSHEET_ID)

        post_id = Get_Post_ID(current_giveaway_link)  #Pull from modmail

        winners = Pick_Winners(num_posts_required, num_prizes_desired, post_id, previous_winners)

        Update_Winners_Spreadsheet(winners, SPREADSHEET_ID, current_giveaway_link)

        Update_Spreadsheet_Values(RANGE_STATUS, SPREADSHEET_ID, [[status["done"]]])



# Updates the spreadsheet with the list of users, comments, and unchecks all the checkboxes in A
def Update_Winners_Spreadsheet(winners, SPREADSHEET_ID, giveaway_link):
    RANGE_USERS_AND_COMMENTS = "Winner_Info"
    RANGE_GIVEAWAY_LINK = "Variables!B3"

    for i in range(len(winners), 50):
        winners.append(["FALSE", "", "", "", "", ""])

    # Make everything else empty

    Update_Spreadsheet_Values(RANGE_USERS_AND_COMMENTS, SPREADSHEET_ID, winners)
    Update_Spreadsheet_Values(RANGE_GIVEAWAY_LINK, SPREADSHEET_ID, [[giveaway_link]])



# This function checks if a potential winner is eligible based on the typical giveaway requirements.
def Check_If_User_Can_Win(num_posts_required, potential_winner, post_id):
    unique_content = []
    unique_posts = []

    post_started = reddit.submission(post_id).created_utc

    try:
        comments, submissions = Get_User_Content(potential_winner, post_started, timedelta(days=365), subreddit, False)

        # Get valid activity
        for entry in submissions + comments:
            post_id = entry[0]
            body = entry[3]
            url = entry[4]
            title = entry[5]

            content = body.split(" ")


            for c in content:
                if any(url_word in c for url_word in ["http", ".com"]):
                    content.remove(c)

            if ( post_id not in unique_posts   and
                 len(content) > 7              and
                 "giveaway" not in title.lower()
            ):
                unique_content.append([body, url])
                unique_posts.append(entry[0])


        if len(unique_posts) >= num_posts_required:
            user_can_win = True
        else:
            user_can_win = False

    except prawcore.exceptions.NotFound:  # User is shadowbanned
        user_can_win = False

    return user_can_win, unique_content



def Check_Modmail_For_Commands():
    # Get the modmails waiting approval from sql
    sql = "SELECT `last_checked_modmail_msg`, `giveaway_id`, `modmail_id`  FROM `giveaway` WHERE `step` BETWEEN 1 AND 4;"
    results = Run_Mysql_Query(sql, None, DB_NAME)

    for result in results:
        commands = {}
        last_checked_modmail_msg = result[0]
        giveaway_id = result[1]
        modmail_id = result[2]
        last_message_found = False

        for message in subreddit.modmail(modmail_id).messages:
            if last_message_found is False:
                if message.id == last_checked_modmail_msg:
                    last_message_found = True

            else:
                if ( message.author in mods and
                     message.author not in bots and
                     message.is_internal is True
                ):
                    body = message.body_markdown

                    split_indexes = [0, len(body)]

                    valid_commands = Get_Giveaway_Commands()

                    for command in valid_commands:
                        try:
                            i = body.index(command)
                            split_indexes.append(i)
                        except ValueError:
                            pass

                    split_indexes.sort()


                    if split_indexes is not None:
                        last_index = 0

                        for index in split_indexes:
                            full_command = body[last_index:index]

                            split_command = full_command.split(" ", 1)

                            if split_command[0] in valid_commands:
                                if len(split_command) > 1:
                                    commands[split_command[0]] = split_command[1]
                                else:
                                    commands[split_command[0]] = None

                            last_index = index

        for command, arguments in commands.items():
            Process_Command(command, arguments, giveaway_id, modmail_id)
            Change_Giveaway("last_checked_msg", message.id, giveaway_id)



def Process_Approval(giveaway_id, modmail_id):
    email = EMAIL
    sql = "SELECT (`prizes`) FROM `giveaway` WHERE `giveaway_id`=%s;"
    values = [giveaway_id]
    result = Run_Mysql_Query(sql, values, DB_NAME)[0]

    prizes_str = ""

    for prize in result[0].split("+"):
        if prize:
            split = prize.split("x")
            if "$" in split[0]:
                prize_qty = split[1]
                prize_val = split[0]
            else:
                prize_qty = split[0]
                prize_val = split[1]

            prizes_str += "\n\n* " + prize_qty + " x " + prize_val + " Amazon.com USD gift cards"


    modmail_message =  giveaway.approval_message


    subreddit.modmail(modmail_id).reply(body=modmail_message, author_hidden=True)
    subreddit.modmail(modmail_id).archive()



def Process_Rejection(modmail_id):
    modmail_message =  giveaway.rejection_message

    subreddit.modmail(modmail_id).reply(body=modmail_message, author_hidden=True)
    subreddit.modmail(modmail_id).archive()



# Checks the website database to see if there are any new giveaway requests
def Check_For_Giveaway_Request():
    sql_request = "SELECT `preferred_end_date`, `preferred_start_date`, `post_link`, `prizes`, `username` FROM `reddit_giveaway_request`;"
    requests = Run_Mysql_Query(sql_request, None, DB_NAME)

    return requests



# Moves the giveaway request from the website to the main database. It also copies the post using the Copy_Users_Post() function. It then deletes the request from the website.
def Move_Giveaway_Request_To_Main_Database(request):
    preferred_end_date = request[0]
    preferred_start_date = request[1]
    post_link = request[2]
    prizes = request[3]
    username = request[4]

    start_index = post_link.index("comments/") + 9
    post_link_split = post_link[start_index:].split("/")
    post_id = post_link_split[0]

    new_post_link = Copy_Users_Post(post_id, None)

    sql_site_name = "SELECT `site_name` FROM `users_site_owners` WHERE username=%s LIMIT 1"
    values = [username]
    site_name = Run_Mysql_Query(sql_site_name, values, DB_USERS)[0][0]


    sql_move_request = "INSERT INTO `giveaway` (`username`, `site_name`, `prizes`, `post`, `start_date`, `end_date`) VALUES (%s, %s, %s, %s, %s, %s);"
    values = [username, site_name, prizes, new_post_link, preferred_start_date, preferred_end_date]

    Run_Mysql_Query(sql_move_request, values, DB_NAME)

    sql_delete_from_original = "DELETE FROM `reddit_giveaway_request` WHERE username=%s"
    values = [username]
    Run_Mysql_Query(sql_delete_from_original, values, DB_NAME)



# Takes a user's post on reddit, copies the content, and then makes a comment on that post with their post in markdown format.
def Copy_Users_Post(post_id, comment_id):
    comment_header = giveaway.comment_header

    if post_id is None:
        post_id = reddit.comment(comment_id).parent_id[3:]

    if post_id != "r6flhu": #Giveaway faq for testing purposes

        post = reddit.submission(id=post_id)

        post_content = post.selftext.replace("\n", "\n    ")
        post_content = "    " + post_content

        post_in_markdown = comment_header + post_content

        if comment_id:
            reddit.comment(comment_id).edit(post_in_markdown)

        else:
            comment = post.reply(post_in_markdown)
            comment.mod.lock()

            new_post_link = comment.id

            return new_post_link
    else:
        return post_id



def End_Giveaway():
    sql = "SELECT `giveaway_post_id`, `giveaway_id` FROM `giveaway` WHERE `end_date`=CURDATE() LIMIT 1"
    result = Run_Mysql_Query(sql, None, DB_NAME)

    if result:
        giveaway = {
            'giveaway_post_id': result[0][0],
            'id': result[0][1]
        }

        giveaway_post = reddit.submission(giveaway['giveaway_post_id'])
        # Edit the post to say giveaway over with a few blank spaces below

        current_giveaway_post = giveaway_post.selftext

        if "GIVEAWAY OVER" not in current_giveaway_post:
            body = "#GIVEAWAY OVER\n\n&nbsp;\n\n----\n\n" + giveaway_post.selftext
            giveaway_post.edit(body)

        giveaway_post.mod.lock()
        giveaway_post.flair.select(XXXX)

        # Update the database
        sql = "UPDATE `giveaway` SET `giveaway_post_id`=%s, `step`=%s WHERE `giveaway_id`=%s;"
        values = [7, giveaway['id']]
        Run_Mysql_Query(sql, values, DB_NAME)



# This function uses the content from an array and returns create a post and title for a giveaway.
# Pre: The site_name, prizes, post content, requirements, and end date are in an array and in appropriate format.
# Post: Title and body for a giveaway content are returned
def Get_Giveaway_Post_Content(giveaway):
    end_date = Format_Date(giveaway['end_date'])
    start_date = Format_Date(datetime.today())

    if giveaway['requirements'] is not None:
        requirements = giveaway['requirements']
        requirements = requirements.replace("%start_date", start_date)
    else:
        requirements = giveaway.requirements
      
    # Title
    prize_total = 0.0

    for prize in giveaway['prizes'].split(","):
        prize = prize.replace("$", "")
        prize_split = prize.split("x")
        prize_total += float(prize_split[0]) * int(prize_split[1])

    if prize_total.is_integer():
        prize_total = '%.0f' % prize_total
    else:
        prize_total = '%.2f' % prize_total


    if giveaway['title'] is None:
        title = giveaway['site_name'] + " | $" + prize_total + " (" + giveaway['prizes'].replace(",", " + ") + ") Gift Card Giveaway!"

    else:
        title = giveaway['title']

        title = title.replace("%site", giveaway['site_name'])
        title = title.replace("%prizes", "$" + prize_total + " (" + giveaway['prizes'].replace(" ", " + ") + ") Gift Card Giveaway!")


    # Body
    body = giveaway['post']

    return title, body



# Returns a list that contains mods, site staff members (from database), users shadowbanned on subreddit, scammers on the USL,
# and anyone who has won any of the past 3 giveaways.
def Get_Ineligible_Users():
    ineligible_users = ["[deleted]"]
    limit_past_giveaways = 3


    # User is a mod
    for mod in subreddit.moderator():
        ineligible_users.append(mod.name)


    # User is a site staff member
    sql = "SELECT `username` FROM `staff`"
    site_staff_members = Run_Mysql_Query(sql, None, DB_USERS)

    for user in site_staff_members:
        ineligible_users.append(user[0])


    # User is on the shadowban list
    automod_config = reddit.subreddit(subreddit.display_name).wiki['config/automoderator']

    for automod_section in automod_config.content_md.split("\n---"):
        if "Shadowban User" in automod_section:
            shadowbanned = automod_section[automod_section.index("[") + 1: automod_section.index("]")].replace(" ", "")

            for user in shadowbanned.split(","):
                if user is not "" and user not in ineligible_users:
                    ineligible_users.append(user)

    # User is on the USL
    scammer_wiki = reddit.subreddit('RSTList').wiki['banlist'].content_md

    scammer_wiki_split = scammer_wiki.split("\n")

    for scammer_line in scammer_wiki_split:
        scammer_line = scammer_line.replace("* /u/", "")
        scammer = scammer_line.split(" ")[0]

        ineligible_users.append(scammer)

    return ineligible_users



# This function sends a modmail to the user informing them of their request and makes a private note with the information for us.
def Send_Initial_Modmail(request):
    preferred_end_date = request[0]
    db_id = request[1]
    post = reddit.comment(request[2]).permalink
    prizes = request[3].replace("+", " + ")
    site_name = request[4]
    preferred_start_date = request[5]
    username = request[6]

    subject = "Giveaway Request"
    msg_to_user =   giveaway.msg_to_user

    internal_note = giveaway.internal_note
  
    modmail = subreddit.modmail.create(subject, msg_to_user, username, author_hidden=True)
    modmail.reply(body=internal_note, internal=True)

    return db_id, modmail.id



# This function will start a giveaway that is scheduled to be posted today.
def Start_Giveaway():
    sql = "SELECT `site_name`, `prizes`, `title`, `post`, `requirements`, `sticky`, `end_date`, `giveaway_id` FROM `giveaway` WHERE `step`=3 AND `start_date`=CURDATE() LIMIT 1"
    result = Run_Mysql_Query(sql, None, DB_NAME)

    if result:
        giveaway = {
            'site_name': result[0][0],
            'prizes': result[0][1],
            'title': result[0][2],
            'post': base64.b64decode(result[0][3]).decode('utf-8'),
            'requirements': result[0][4],
            'sticky': result[0][5],
            'end_date': result[0][6],
            'id': result[0][7]
        }

        giveaway_posted = False

        recent_submissions = reddit.redditor(BOT_USERNAME).submissions.new()

        # Make sure we didn't already make the post
        for submission in recent_submissions:
            if submission.created_utc > (datetime.now() - timedelta(days=2)).timestamp():
                if giveaway['title'] == submission.title:
                    giveaway_posted = submission
                    break


        if giveaway_posted:
            post = reddit.submission(giveaway_posted)
            title = post.title

        else:
            title, body = Get_Giveaway_Post_Content(giveaway)
            post = subreddit.submit(title=title, selftext=body, flair_id="XXXX")

        post.mod.approve()
        post.mod.contest_mode(state=True)
        post.mod.distinguish(how="yes")

        if giveaway['sticky'] == 1:
            post.mod.sticky(state=True, bottom=True)


        # Update the database
        sql = "UPDATE `giveaway` SET `giveaway_post_id`=%s, `step`=%s, `title`=%s WHERE `giveaway_id`=%s;"
        values = [post.id, 4, title, giveaway['id']]
        Run_Mysql_Query(sql, values, DB_NAME)



def Get_Giveaway_Commands():
    valid_commands = ["!confirm", "!post", "!prizes", "!reject", "!requirements", "!sticky", "!title" ]

    return valid_commands



def Format_Prizes(current_format):
    prize_formatted = ""
    prize_sets = current_format.split("+")

    for i, prize_set in enumerate(prize_sets):
        split = prize_set.split("x")
        if "$" in split[0]:
            prize_qty = split[1]
            prize_val = split[0]
        else:
            prize_qty = split[0]
            prize_val = split[1]

        if i > 0:
            prize_formatted += "+"
        prize_formatted += prize_val + "x" + prize_qty

    return prize_formatted




def Process_Command(command, arguments, giveaway_id, modmail_id):
    command = command.lower()
    giveaway_steps = GiveawaySteps()
    step = "!step"

    if command == "!confirm":
        Process_Approval(giveaway_id, modmail_id)
        Change_Giveaway(command=step, change_to=giveaway_steps.approved, giveaway_id=giveaway_id)

    elif command == "!post":
        sql = "SELECT `post` FROM `giveaway` WHERE `giveaway_id`=%s;"
        values = [giveaway_id]
        comment_id = Run_Mysql_Query(sql, values, DB_NAME)[0][0]

        Copy_Users_Post(None, comment_id)

    elif command == "!prizes":
        prizes = Format_Prizes(arguments)
        Change_Giveaway(command, prizes, giveaway_id)

    elif command == "!reject":
        Process_Rejection(modmail_id)
        Change_Giveaway(command=step, change_to=giveaway_steps.rejected, giveaway_id=giveaway_id)

    elif command ==  "!sticky":
        if arguments.lower() == "true":
            Change_Giveaway(command, 1, giveaway_id)
        elif arguments.lower() == "false":
            Change_Giveaway(command, 0, giveaway_id)

    elif command in ["!requirements", "!title"]:
        Change_Giveaway(command, arguments, giveaway_id)



def Change_Giveaway(command, change_to, giveaway_id):
    valid_commands = {
        "!end_date": "end_date",
        "!prizes": "prizes",
        "!requirements": "requirements",
        "!start_date": "start_date",
        "!step": "step",
        "!sticky": "sticky",
        "!title": "title",

        "last_checked_msg": "last_checked_modmail_msg"
    }

    sql = "UPDATE `giveaway` SET `" + valid_commands[command] + "`=%s WHERE `giveaway_id`=%s;"
    values = [change_to, giveaway_id]
    Run_Mysql_Query(sql, values, DB_NAME)



def Check_If_Giveaway_Starts_Today():
    sql = "SELECT `giveaway_id` FROM `giveaway` WHERE `step`=3 AND `start_date`=CURDATE() LIMIT 1"
    giveaway = Run_Mysql_Query(sql, None, DB_NAME)

    return True if giveaway else False



def Check_If_Giveaway_Ends_Today():
    sql = "SELECT `giveaway_id` FROM `giveaway` WHERE `step`=3 AND `end_date`=CURDATE() LIMIT 1"
    giveaway = Run_Mysql_Query(sql, None, DB_NAME)

    return True if giveaway else False



def Format_Winner_Activity(unique_posts):
    cont = " (continued...)"
    formatted_activty = ""
    max_characters = 80
    max_content_entries = 4
    newline = "\n"

    for i, entry in enumerate(unique_posts[0:max_content_entries]):
        content = entry[0]
        permalink = entry[1]

        content = content.replace("\n", " ")

        if i > 0:
            formatted_activty += newline + newline

        formatted_activty += str(content[0:max_characters])

        if len(content) > max_characters:
            formatted_activty += cont

        formatted_activty += newline + permalink
    print(formatted_activty)

    return formatted_activty




def Pick_Winners(num_posts_required, num_winners, post_id, previous_winners):
    entries = []
    winners = previous_winners
    ineligible_users = Get_Ineligible_Users()

    print("Picking Giveaway Winners")

    for winner in winners:
        entries.append([winner[0], winner[1]])


    for comment in reddit.submission(post_id).comments:
        if comment.parent_id == comment.link_id   and   comment.banned_by is None:
            if( comment.author is not None and
                not any(comment.author.name in a for a in entries) and
                comment.author.name not in ineligible_users
            ):
                entries.append([comment.author.name, comment.body])


    while len(winners) < num_winners and len(entries) > 0:
        potential_winners = random.sample(entries, 1)

        for potential_winner in potential_winners:
            user_can_win, unique_content = Check_If_User_Can_Win(num_posts_required, potential_winner[0], post_id)

            if user_can_win:
                comment_karma = reddit.redditor(potential_winner[0]).comment_karma
                link_karma = reddit.redditor(potential_winner[0]).link_karma

                formatted_activity = Format_Winner_Activity(unique_content)

                winners.append(["FALSE", potential_winner[0], comment_karma, link_karma, potential_winner[1], formatted_activity])
                print("Winner found: " + str(len(winners)) + "/" + str(num_winners) + " - u/" + potential_winner[0])

            entries.remove(potential_winner)


    return winners



def Update_Automod_New_Account_On_Giveaway_Removal(post_id):
    phrase = "%%giveaway-handler%%"
    automod_page = subreddit.wiki["config/automoderator"]
    content_md = automod_page.content_md

    phrase_index = content_md.index(phrase)
    id_index = content_md[phrase_index:].index("id:") + content_md.index(phrase)
    start_bracket = content_md[id_index:].index('[') + id_index + 1
    end_bracket = content_md[start_bracket:].index(']') + start_bracket
    ids = content_md[start_bracket:end_bracket]


    if " " not in ids:
        updated_ids = '"' + post_id + '"'
    else:
        updated_ids = ids + ', "' + post_id + '"'

    if ids != updated_ids:
        content = content_md[:start_bracket] + updated_ids + content_md[end_bracket:]

        automod_page.edit(content=content, reason="Update id for giveaway", previous="{" + automod_page.revision_id + "}")



def Update_Giveaway_Request_With_Post_Id(giveaway_id):
    giveaway_post_made_step = GiveawaySteps().post_made

    sql = "UPDATE `giveaway` " + \
          "SET `giveaway_post_id`=%s, `step`=%s " + \
          "WHERE `step` IN (2, 3) AND `start_date` <= NOW();"
    values = [giveaway_id, giveaway_post_made_step]
    Run_Mysql_Query(database=DB_NAME, sql=sql, values=values)
