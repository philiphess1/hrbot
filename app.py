from flask import Flask, render_template, request, redirect, url_for, jsonify, g, flash, session
from flask_login import login_required, LoginManager, login_user, UserMixin, logout_user, current_user
from langchain_pinecone import Pinecone
from pinecone import Pinecone as PineconeClient
from azure.storage.blob import BlobServiceClient, BlobClient, ContainerClient, ContentSettings
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.prompts import ChatPromptTemplate, PromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
from langchain_core.messages import get_buffer_string
from operator import itemgetter
from langchain.schema import format_document
from langchain.memory import ConversationBufferMemory
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.decomposition import TruncatedSVD
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import Normalizer
from sklearn.cluster import KMeans
import os
import tiktoken
from dotenv import load_dotenv
from io import BytesIO
from PyPDF2 import PdfReader
import docx2txt
import pandas as pd
import requests
import re
from bs4 import BeautifulSoup
from werkzeug.utils import secure_filename
import psycopg2
import bcrypt
from flask_session import Session
import pandas as pd
from itsdangerous import URLSafeTimedSerializer
from flask_mail import Mail, Message
import pickle
import stripe
from stripe.error import SignatureVerificationError


load_dotenv()

app = Flask(__name__)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SECRET_KEY'] = 'your_secret_key_here'
Session(app)

app.config['SECURITY_PASSWORD_SALT'] = os.getenv('SECURITY_PASSWORD_SALT')
app.config['MAIL_SERVER'] = os.getenv('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.getenv('MAIL_PORT'))
app.config['MAIL_USE_SSL'] = os.getenv('MAIL_USE_SSL') == 'True'
app.config['MAIL_USERNAME'] = os.getenv('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.getenv('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.getenv('MAIL_DEFAULT_SENDER')
mail = Mail(app)
s = URLSafeTimedSerializer(app.config['SECRET_KEY'])

connection_string = os.getenv('AZURE_CONNECTION_STRING')
container_name = os.getenv('AZURE_CONTAINER_NAME')

stripe.api_key = os.getenv('STRIPE_API_KEY')
endpoint_secret = os.getenv('ENDPOINT_SECRET')

openai_api_key = os.getenv("OPENAI_API_KEY")

database_url = os.getenv('DATABASE_URL')

environment = os.getenv("PINECONE_ENVIRONMENT")
pinecone_api_key = os.getenv("PINECONE_API_KEY")
index_name= os.getenv("PINECONE_INDEX")
index_host = os.getenv("PINECONE_HOST")


pc = PineconeClient(api_key=pinecone_api_key)
index = pc.Index(index_name)
text_field="text"
embeddings = OpenAIEmbeddings(openai_api_key=openai_api_key)


def get_bot_temperature(user_id, chatbot_id):
    with g.db_conn.cursor() as cursor:
        cursor.execute("SELECT bot_temperature FROM chatbot_settings WHERE user_id = %s AND id = %s;", (user_id, chatbot_id))
        row = cursor.fetchone()
        return row[0] if row else 0.0
    

def get_custom_prompt(user_id, chatbot_id):
    with g.db_conn.cursor() as cursor:
        cursor.execute("SELECT custom_prompt FROM chatbot_settings WHERE user_id = %s AND id = %s;", (user_id, chatbot_id))
        row = cursor.fetchone()
        return row[0] if row else "Default prompt part"


# Initialize Flask-Login
app.secret_key = os.getenv('SECRET_KEY')
login_manager = LoginManager()
login_manager.init_app(app)

class AuthenticatedUser(UserMixin):
    def __init__(self, id):
        self.id = id

@app.before_request
def before_request():
    g.db_conn = psycopg2.connect(database_url)
    g.cursor = g.db_conn.cursor()

@app.teardown_request
def teardown_request(exception):
    cursor = getattr(g, 'cursor', None)
    if cursor is not None:
        cursor.close()
    db_conn = getattr(g, 'db_conn', None)
    if db_conn is not None:
        db_conn.close()

@login_manager.user_loader
def load_user(user_id):
    g.cursor.execute("SELECT id FROM users WHERE id = %s", (user_id,))
    user_data = g.cursor.fetchone()
    if user_data:
        return AuthenticatedUser(id=user_data[0])
    return None

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        email = request.form['email']
        code = request.form['code']

        # Check if the invitation exists
        g.cursor.execute("SELECT email FROM invitations WHERE email = %s AND code = %s", (email, code))
        if not g.cursor.fetchone():
            flash('Invalid email or code', 'error')
            return redirect(url_for('signup'))

        # Check if user already exists
        g.cursor.execute("SELECT id FROM users WHERE username = %s OR email = %s", (username, email))
        if g.cursor.fetchone():
            flash('Username or email already exists', 'error')
            return redirect(url_for('signup'))

        # Hash the password
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        hashed_password = hashed_password.decode('utf-8')

        # Insert new user into the database
        g.cursor.execute("INSERT INTO users (username, password, email) VALUES (%s, %s, %s)", (username, hashed_password, email))
        g.db_conn.commit()

        # Delete the used invitation
        g.cursor.execute("DELETE FROM invitations WHERE email = %s", (email,))
        g.db_conn.commit()

        flash('Account created successfully!', 'success')
        return redirect(url_for('login'))

    return render_template('signup.html')

@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = request.form['email']

        # Check if email exists in the database
        g.cursor.execute("SELECT id, name FROM public.users WHERE email = %s", (email,))
        user_data = g.cursor.fetchone()
        if not user_data:
            flash('No account associated with that email address', 'error')
            return redirect(url_for('forgot_password'))

        # Generate a password reset token
        token = s.dumps(email, salt=app.config['SECURITY_PASSWORD_SALT'])

        # Save the token in the database
        g.cursor.execute("INSERT INTO public.password_resets (user_id, token) VALUES (%s, %s)", (user_data[0], token))
        g.db_conn.commit()

        # Create a password reset link with the token
        reset_link = url_for('reset_password', token=token, _external=True)

        # Send an email to the user with the reset link
        msg = Message('Password Reset Requested', recipients=[email])
        msg.html = render_template('reset_password_email.html', reset_link=reset_link, name=user_data[1])
        mail.send(msg)

        flash('Password reset link sent to your email address', 'success')
        return redirect(url_for('login'))

    return render_template('forgot_password.html')

@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    try:
        # Validate the password reset token
        email = s.loads(token, salt=app.config['SECURITY_PASSWORD_SALT'], max_age=3600)
        app.logger.info(f"Email from token: {email}")
    except Exception as e:
        app.logger.error(f"Error validating token: {e}")
        flash('The password reset link is invalid or has expired', 'error')
        return redirect(url_for('login'))

    # Check if the token exists in the database
    g.cursor.execute("SELECT user_id FROM public.password_resets WHERE token = %s", (token,))
    user_data = g.cursor.fetchone()
    if not user_data:
        app.logger.error(f"Token not found in database: {token}")
        flash('The password reset link is invalid or has expired', 'error')
        return redirect(url_for('login'))

    if request.method == 'POST':
        password = request.form['password']

        # Hash the new password
        hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
        hashed_password = hashed_password.decode('utf-8')

        # Update the user's password in the database
        g.cursor.execute("UPDATE public.users SET password = %s WHERE id = %s", (hashed_password, user_data[0]))
        g.db_conn.commit()

        # Delete the token from the database
        g.cursor.execute("DELETE FROM public.password_resets WHERE token = %s", (token,))
        g.db_conn.commit()

        flash('Your password has been updated!', 'success')
        return redirect(url_for('login'))

    return render_template('reset_password.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].lower()
        password = request.form['password']
        
        g.cursor.execute("SELECT id, password FROM users WHERE LOWER(email) = %s", (email,))
        user_data = g.cursor.fetchone()
        
        if user_data:
            stored_password = user_data[1]
            if stored_password:
                try:
                    if bcrypt.checkpw(password.encode('utf-8'), stored_password.encode('utf-8')):
                        user = AuthenticatedUser(id=user_data[0])
                        login_user(user)
                        return redirect('/')
                    else:  # Passwords do not match
                        flash('Invalid password', 'error')
                except ValueError:  # Invalid bcrypt salt
                    flash('Invalid password', 'error')
            else:  
                flash('Invalid password', 'error')  # Stored Password is None
        else:
            flash('Invalid email', 'error')  # Change this line
            
    return render_template('login.html')

@app.route('/subscription', methods=['POST'])
def update_subscription():
    payload = request.get_data(as_text=True)
    sig_header = request.headers.get('STRIPE_SIGNATURE')

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, endpoint_secret
        )
    except ValueError as e:
        # Invalid payload
        return jsonify(success=False), 400
    except SignatureVerificationError as e:
        # Invalid signature
        return jsonify(success=False), 400
    
    if event['type'] == 'customer.subscription.deleted':
        subscription = event['data']['object']
        customer_id = subscription['customer']

        # Set the user's subscription_item_id to null in the database
        g.cursor.execute("UPDATE users SET subscription_item_id = NULL WHERE stripe_customer_id = %s", (customer_id,))
        g.db_conn.commit()

    if event['type'] == 'customer.subscription.updated':
        subscription = event['data']['object']
        customer_id = subscription['customer']
        subscription_item_id = subscription['items']['data'][0]['id']

        # Update the user's subscription_item_id in the database
        g.cursor.execute("UPDATE users SET subscription_item_id = %s WHERE stripe_customer_id = %s", (subscription_item_id, customer_id))
        g.db_conn.commit()
    
    if event['type'] == 'checkout.session.completed':
        subscription = event['data']['object']
        customer_email = subscription['customer_details']['email']
        customer_id = subscription['customer']
        customer_name = subscription['customer_details']['name']
        subscription_id = subscription['subscription']
        stripe_subscription = stripe.Subscription.retrieve(subscription_id)
        subscription_item_id = stripe_subscription['items']['data'][0]['id']

        # Print statements
        print(f'Customer Email: {customer_email}')
        print(f'Customer Name: {customer_name}')
        print(f'Stripe Customer ID: {customer_id}')
        print(f'Subscription ID: {subscription_id}')
        print(f'Subscription Item ID: {subscription_item_id}')

        # Check if user already exists
        g.cursor.execute("SELECT id FROM users WHERE email = %s", (customer_email,))
        user_data = g.cursor.fetchone()

        if user_data:
            # User exists, update their subscription_item_id
            g.cursor.execute("UPDATE users SET subscription_item_id = %s WHERE id = %s", (subscription_item_id, user_data[0]))
        else:
            # User does not exist, create a new user record
            g.cursor.execute("INSERT INTO users (email, name, subscription_item_id, stripe_customer_id) VALUES (%s, %s, %s, %s) RETURNING id", (customer_email, customer_name, subscription_item_id, customer_id))
            user_id = g.cursor.fetchone()[0]

            # Generate a password reset token
            token = s.dumps(customer_email, salt=app.config['SECURITY_PASSWORD_SALT'])

            # Save the token in the database
            g.cursor.execute("INSERT INTO public.password_resets (user_id, token) VALUES (%s, %s)", (user_id, token))
            g.db_conn.commit()

            # Create a password reset link with the token
            reset_link = url_for('reset_password', token=token, _external=True)

            # Send an email to the user with the reset link
            msg = Message('Password Update Requested', recipients=[customer_email])
            msg.html = render_template('reset_password_email.html', reset_link=reset_link, name=customer_name)
            mail.send(msg)

        g.db_conn.commit()

    return jsonify(success=True)

@app.route('/', methods=['GET'])
@login_required
def home():
    # Fetch the chatbot settings for the current user
    g.cursor.execute("SELECT id, chatbot_name FROM chatbot_settings WHERE user_id = %s", (current_user.id,))
    chatbots = g.cursor.fetchall()

    g.cursor.execute("SELECT COUNT(*) FROM feedback WHERE user_id = %s", (current_user.id,))
    count = g.cursor.fetchone()[0]

    # Pass the chatbot settings to the template
    return render_template('home.html', chatbots=chatbots, count=count, user_id=current_user.id)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))

@app.route('/<int:user_id>/<int:chatbot_id>')
def chatbot(user_id, chatbot_id):
    print(f"session ID: {session.sid}")
    session[f'memory_{session.sid}'] = pickle.dumps(None)
    print()

    # Query PostgreSQL to get the settings
    g.cursor.execute("SELECT widget_icon_url, background_color, font_style, bot_temperature, greeting_message, custom_prompt, dot_color, logo, chatbot_title, title_color, border_color,primary_color,secondary_color,suggested_questions FROM chatbot_settings WHERE user_id = %s AND id = %s;", (user_id, chatbot_id,))
    row = g.cursor.fetchone()
    if row is None:
        settings = {
            'widget_icon': 'ecco_icon',  # Default values if no settings are found for the user
            'background_color': '#ffffff',
            'font_style': 'Arial',
            'bot_temperature': 0.3,
            'greeting_message': 'Hello! I am Ecco, your AI assistant. How can I help you today?',
            'custom_prompt': """
I want you to act as a funny and friendly customer support AI from my company. Your name is “Assistant AI". You limit your knowledge to the context provided. You will provide me with accurate answers related to my company only from your context. You will be as detailed as possible. Do not make up answers. Refuse to answer any question not about the documents or my company. Never break character. Always answer in the language of my message. Please use simple formatting. Answer like you are part of the team using we/us and not they. Give hyperlinks when needed.

RESTRICTIONS:
Do NOT say "Based on the given information.
Do not makeup answers if you are not sure about the answer. If you don't know the answer, say "I'm not sure about this, could you please send us an email at contact@mycompany.com" and stop after that.
""",
            'dot_color': '#555555',
            'logo': 'https://app.eccoai.org/static/images/ecco_icon.png',
            'chatbot_title': 'EccoAI',
            'title_color': '#000000',
            'border_color': '#ffffff',
        }
    else:
        settings = {
            'widget_icon': row[0],
            'background_color': row[1],
            'font_style': row[2],
            'bot_temperature': row[3],
            'greeting_message': row[4],
            'custom_prompt': row[5],
            'dot_color': row[6],
            'logo': row[7],
            'chatbot_title': row[8],
            'title_color': row[9],
            'border_color': row[10],
            'primary_color':row[11],
            'secondary_color':row[12],
            'suggested_questions':row[13],
        }

    return render_template('index.html', settings=settings, user_id=user_id)

@app.route('/<int:user_id>/<int:chatbot_id>/chat', methods=['POST'])
def chat(user_id, chatbot_id):
    vectorstore = Pinecone(
        index, embeddings, text_field,  namespace=f"{user_id}{chatbot_id}"
    )

    user_message = request.form.get('message')

    retriever = vectorstore.as_retriever(
            search_type = "similarity_score_threshold",
            search_kwargs={'score_threshold': 0.7, 'k': 5},
        )

    if f'memory_{session.sid}' in session:
        memory = pickle.loads(session[f'memory_{session.sid}'])
    else:
        memory = ConversationBufferMemory(
            return_messages=True, output_key="answer", input_key="question"
        )

    if memory is None:
        memory = ConversationBufferMemory(
            return_messages=True, output_key="answer", input_key="question"
        )

    bot_temperature = get_bot_temperature(user_id, chatbot_id)
    custom_prompt = get_custom_prompt(user_id, chatbot_id)

    llm = ChatOpenAI(
        openai_api_key=openai_api_key,
        model_name='gpt-3.5-turbo',
        temperature=bot_temperature
    )

    DEFAULT_DOCUMENT_PROMPT = PromptTemplate.from_template(template="{page_content}")

    def _combine_documents(
        docs, document_prompt=DEFAULT_DOCUMENT_PROMPT, document_separator="\n\n"
    ):
        doc_strings = [format_document(doc, document_prompt) for doc in docs]
        return document_separator.join(doc_strings)
    
    
    _template = """Given the following conversation and a follow up question, rephrase the follow up question to be a standalone question, in its original language.

    Chat History:
    {chat_history}
    Follow Up Input: {question}
    Standalone question:"""
    CONDENSE_QUESTION_PROMPT = PromptTemplate.from_template(_template)

    template = f"""{custom_prompt}

    Answer the question based only on the following context:
    {{context}}

    Question: {{question}}
    """
    ANSWER_PROMPT = ChatPromptTemplate.from_template(template)

    # First we add a step to load memory
    # This adds a "memory" key to the input object
    loaded_memory = RunnablePassthrough.assign(
        chat_history=RunnableLambda(memory.load_memory_variables) | itemgetter("history"),
    )
    # Now we calculate the standalone question
    standalone_question = {
        "standalone_question": {
            "question": lambda x: x["question"],
            "chat_history": lambda x: get_buffer_string(x["chat_history"]),
        }
        | CONDENSE_QUESTION_PROMPT
        | llm
        | StrOutputParser(),
    }
    # Now we retrieve the documents
    retrieved_documents = {
        "docs": itemgetter("standalone_question") | retriever,
        "question": lambda x: x["standalone_question"],
    }
    # Now we construct the inputs for the final prompt
    final_inputs = {
        "context": lambda x: _combine_documents(x["docs"]),
        "question": itemgetter("question"),
    }
    # And finally, we do the part that returns the answers
    answer = {
        "answer": final_inputs | ANSWER_PROMPT | ChatOpenAI(),
        "docs": itemgetter("docs"),
    }
    # And now we put it all together!
    final_chain = loaded_memory | standalone_question | retrieved_documents | answer

    inputs = {"question": user_message}
    result = final_chain.invoke(inputs)
    print(result)
    memory.save_context(inputs, {"answer": result["answer"].content})

    print("*"*100)
    print(session)
    print("*"*100)

    response = result['answer']
    docs = result['docs']
    # Convert the AIMessage to a dictionary
    filenames = [doc.metadata['filename'] for doc in docs]
    response_dict = {
        'content': response.content,
        'sources': filenames,
        # Add any other fields as necessary
    }
    # Save the memory back to the session at the end of the request
    session[f'memory_{session.sid}'] = pickle.dumps(memory)

    # Print the contents of the memory
    print(f"Memory for user {session.sid}: {memory}")
    print("*"*100)



    print(response_dict)
    return jsonify(response_dict)

@app.route('/<int:user_id>/<int:chatbot_id>/store_feedback', methods=['POST'])
def store_feedback(user_id, chatbot_id):
    data = request.json
    feedback_type = data.get('feedback_type')
    bot_response = data.get('bot_response')
    user_question = data.get('user_question')
    record_id = data.get('id')  
    
    try:
        g.cursor.execute(
            "UPDATE feedback SET user_question = %s, bot_response = %s, feedback_type = %s, user_id = %s, chatbot_id = %s WHERE id = %s",
            (user_question, bot_response, feedback_type, user_id, chatbot_id, record_id)
        )
        g.db_conn.commit()
        return jsonify({"message": "Feedback stored successfully!"})
    except Exception as e:
        print(f"Error storing feedback: {e}")
        return jsonify({"message": "Error storing feedback"}), 500

@app.route('/<int:user_id>/<int:chatbot_id>/store_qa', methods=['POST'])
def store_qa(user_id, chatbot_id):
    data = request.json
    question = data.get('question')
    answer = data.get('answer')
    
    try:
        g.cursor.execute(
            "INSERT INTO feedback (user_question, bot_response, user_id, chatbot_id, feedback_type) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (question, answer, user_id, chatbot_id, None)
        )
        record_id = g.cursor.fetchone()[0]
        g.db_conn.commit()
        return jsonify({"message": "Question and answer stored successfully!", "id": record_id})
    except Exception as e:
        print(f"Error storing question and answer: {e}")
        return jsonify({"message": "Error storing question and answer"}), 500

@app.route('/<int:chatbot_id>/admin')
@login_required
def admin(chatbot_id):
    if current_user.is_authenticated:
        user_id = current_user.id
    else:
        # Redirect to the login page
        return redirect(url_for('login'))

    # Query PostgreSQL to get the list of documents
    g.cursor.execute("SELECT id, filename, file_size, upload_date FROM document_mapping WHERE user_id = %s AND chatbot_id = %s;", (user_id, chatbot_id))
    documents = [{'id': row[0], 'name': row[1], 'size': round(row[2], 3), 'date_added': row[3]} for row in g.cursor.fetchall()]

    # Query for chatbot settings
    g.cursor.execute("SELECT widget_icon_url, background_color, font_style, bot_temperature, greeting_message, custom_prompt, dot_color, logo, chatbot_title, title_color, border_color FROM chatbot_settings WHERE user_id = %s AND id = %s;", (user_id, chatbot_id))
    row = g.cursor.fetchone()

    if row is None:
        # Insert default settings for new user
        default_settings = (
            'ecco_icon',  # Default widget icon URL
            '#ffffff',      # Default background color
            'Arial',        # Default font style
            0.3,            # Default bot temperature
            'Hello! I am Ecco, your AI assistant. How can I help you today?',  # Default greeting message
            """
I want you to act as a funny and friendly customer support AI from my company. Your name is “Assistant AI". You limit your knowledge to the context provided. You will provide me with accurate answers related to my company only from your context. You will be as detailed as possible. Do not make up answers. Refuse to answer any question not about the documents or my company. Never break character. Always answer in the language of my message. Please use simple formatting. Answer like you are part of the team using we/us and not they. Give hyperlinks when needed.

RESTRICTIONS:
Do NOT say "Based on the given information.
Do not makeup answers if you are not sure about the answer. If you don't know the answer, say "I'm not sure about this, could you please send us an email at contact@mycompany.com" and stop after that.
""",
            '#555555', #'dot_color'
            'https://app.eccoai.org/static/images/ecco_icon.png', #'logo'
            'EccoAI', #'chatbot_title'
            '#000000', #'title_color'
            '#ffffff' #'border_color'
        )
        g.cursor.execute("INSERT INTO chatbot_settings (user_id, widget_icon_url, background_color, font_style, bot_temperature, greeting_message, custom_prompt, dot_color, logo, chatbot_title, title_color, border_color) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s);", (user_id,) + default_settings)
        g.db_conn.commit()
        settings = dict(zip(['widget_icon', 'background_color', 'font_style', 'bot_temperature', 'greeting_message', 'custom_prompt', 'dot_color', 'logo', 'chatbot_title', 'title_color', 'border_color'], default_settings))
    else:
        settings = {
            'widget_icon': row[0],
            'background_color': row[1],
            'font_style': row[2],
            'bot_temperature': row[3],
            'greeting_message': row[4],
            'custom_prompt': row[5],
            'dot_color': row[6],
            'logo': row[7],
            'chatbot_title': row[8],
            'title_color': row[9],
            'border_color': row[10],
        }

    return render_template('admin.html', documents=documents, settings=settings, user_id=user_id, chatbot_id=chatbot_id)


@app.route('/<int:chatbot_id>/integrations')
@login_required
def integrations(chatbot_id):
    user_id = current_user.id
    g.cursor.execute("SELECT widget_icon_url, background_color, font_style, bot_temperature, greeting_message, custom_prompt, dot_color, logo, chatbot_title, title_color, border_color,primary_color,secondary_color FROM chatbot_settings WHERE user_id = %s AND id = %s;", (user_id, chatbot_id))
    row = g.cursor.fetchone()
    if row is None:
        settings = {
            'widget_icon': 'chatboticon',  # Default values if no settings are found for the user
            'background_color': '#ffffff',
            'font_style': 'Arial',
            'bot_temperature': 0.0,
            'greeting_message': 'Hello! I am Ecco, your AI assistant. How can I help you today?',
            'custom_prompt': """
            I want you to act as a funny and friendly customer support AI from my company. Your name is “Assistant AI". You limit your knowledge to the context provided. You will provide me with accurate answers related to my company only from your context. You will be as detailed as possible. Do not make up answers. Refuse to answer any question not about the documents or my company. Never break character. Always answer in the language of my message. Please use simple formatting. Answer like you are part of the team using we/us and not they. Give hyperlinks when needed.

            RESTRICTIONS:
            Do NOT say "Based on the given information.
            Do not makeup answers if you are not sure about the answer. If you don't know the answer, say "I'm not sure about this, could you please send us an email at contact@mycompany.com" and stop after that.
            """,
            'dot_color': '#555555',
            'logo': 'https://app.eccoai.org/static/images/ecco_icon.png',
            'chatbot_title': 'EccoAI',
            'title_color': '#000000',
            'border_color': '#ffffff',
            'primary_color':'#B2E24C',
            'secondary_color':'#80A12C',
        }
    else:
        settings = {
            'widget_icon': row[0],
            'background_color': row[1],
            'font_style': row[2],
            'bot_temperature': row[3],
            'greeting_message': row[4],
            'custom_prompt': row[5],
            'dot_color': row[6],
            'logo': row[7],
            'chatbot_title': row[8],
            'title_color': row[9],
            'border_color': row[10],
            'primary_color':row[11],
            'secondary_color':row[12],
        }
    return render_template('integrations.html', settings=settings, user_id=user_id, chatbot_id=chatbot_id)

@app.route('/<int:chatbot_id>/upload', methods=['POST'])
def upload_file(chatbot_id):
    uploaded_files = request.files.getlist('file')
    user_id = current_user.id
    for file in uploaded_files:
        if file.filename != '':
            filename = secure_filename(file.filename)
            file_size = len(file.read())
            
            # Reset the file position to the beginning
            file.seek(0)

            file_size = file_size/1000000

            g.cursor.execute("INSERT INTO document_mapping (filename, file_size, user_id, chatbot_id) VALUES (%s, %s, %s, %s) RETURNING id;", (filename, file_size, user_id, chatbot_id))
            g.db_conn.commit()

            # Create a BytesIO stream from the uploaded file
            file_stream = BytesIO(file.read())
            file_extension = filename.split(".")[-1].lower()

            if file_extension == "pdf":
                pdf_reader = PdfReader(file_stream)
                num_pages = len(pdf_reader.pages)
                for page_num in range(num_pages):
                    page = pdf_reader.pages[page_num]
                    text = page.extract_text()
                    process_text(text, filename, page_num,f"{user_id}", f"{chatbot_id}")

            elif file_extension == "docx":
                doc = docx2txt.process(file_stream)
                cleaned_doc = re.sub(r'\s+', ' ', doc.strip())
                process_text(cleaned_doc, filename, 0,f"{user_id}", f"{chatbot_id}")

            elif file_extension == "xlsx":
                # use pandas to read the excel file from the bytesIO steam
                df = pd.read_excel(file_stream)
                headers = ' '.join(df.columns) + '\n'
                full_text = df.to_string(index=False, header=False)
                process_excel_text(full_text, headers, filename,f"{user_id}", f"{chatbot_id}")

            elif file_extension == "csv":
                # use pandas to read the excel file from the bytesIO steam
                encodings = ['utf-8', 'latin1', 'iso-8859-1', 'cp1252']
                for encoding in encodings:
                    try:
                        df = pd.read_csv(file_stream, encoding=encoding)
                        headers = ' '.join(df.columns) + '\n'
                        full_text = df.to_string(index=False, header=False)
                        process_excel_text(full_text, headers, filename,f"{user_id}", f"{chatbot_id}")
                        break
                    except UnicodeDecodeError:
                        continue
                    except pd.errors.EmptyDataError:
                        return jsonify({"status": "error", "message": "File is empty or incorrectly formatted!"})
            
    return jsonify({"status": "success", "message": "Files uploaded successfully!"})

def process_text(text, filename, page_num, user_id, chatbot_id):
    # Process the text (i.e., break it into chunks and create embeddings)
    chunk_size = 750
    overlap = 100
    for start in range(0, len(text), chunk_size - overlap):
        end = start + chunk_size
        text_chunk = text[start:end]
        print(text_chunk)

        # Generate embeddings
        embedding = embeddings.embed_query(text_chunk)

        # Create a chunk ID
        chunk_doc_id = f"{filename}_page{page_num}_start{start}:{end}"

        # Prepare data for Pinecone
        upsert_data = [(chunk_doc_id, embedding, {"filename": filename, "text": text_chunk})]
        
        # Store the embeddings in Pinecone using 'upsert' method
        index.upsert(upsert_data, namespace=f"{user_id}{chatbot_id}")

def process_excel_text(full_text, headers, filename,user_id, chatbot_id):
    chunk_size = 750
    overlap = 100
    for start in range(0, len(full_text), chunk_size - overlap):
        end = start + chunk_size
        text_chunk = full_text[start:end]
        text_chunk = headers + text_chunk
        print(text_chunk)
        # Generate embeddings
        embedding = embeddings.embed_query(text_chunk)

        # Create a chunk ID
        chunk_doc_id = f"{filename}_start{start}:{end}"


        # Prepare data for Pinecone
        upsert_data = [(chunk_doc_id, embedding, {"filename": filename, "text": text_chunk})]
        
        # Store the embeddings in Pinecone using 'upsert' method
        index.upsert(upsert_data, namespace=f"{user_id}{chatbot_id}")


@app.route('/<int:chatbot_id>/scrape', methods=['POST'])
@login_required
def scrape_url(chatbot_id):
    url = request.form['url']
    user_id = current_user.id
    try:
        response = requests.get(url)
        raw_html = response.text
        print(f"Raw HTML: {raw_html}")  # Print raw HTML

        soup = BeautifulSoup(raw_html, 'html.parser')

        # Remove script and style elements
        for script in soup(["script", "style"]):
            script.extract()

        # Get text
        text = soup.get_text()
        print(f"Text after removing script and style elements: {text}")  # Print text after removing script and style elements

        # Break into lines and remove leading and trailing space on each
        lines = (line.strip() for line in text.splitlines())
        # Break multi-headlines into a line each
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        # Drop blank lines
        text = '\n'.join(chunk for chunk in chunks if chunk)
        print(f"Final text: {text}")  # Print final text

        # Calculate file size
        file_size = len(text.encode('utf-8'))/1000000
        print(f"File size: {file_size}")  # Print file size

        # Insert into database
        g.cursor.execute("INSERT INTO document_mapping (filename, file_size, user_id, chatbot_id) VALUES (%s, %s, %s, %s) RETURNING id;", (url, file_size, user_id, chatbot_id))
        g.db_conn.commit()

        # Process the text and put it in the vector database
        process_text(text, url, 0, f"{user_id}", f"{chatbot_id}")

        return redirect(url_for('admin', chatbot_id=chatbot_id))

    except requests.RequestException as e:
        return jsonify({"status": "error", "message": f"Error processing URL: {str(e)}"})
    except Exception as e:
        return jsonify({"status": "error", "message": f"Unexpected error: {str(e)}"})


@app.route('/<int:chatbot_id>/delete/<doc_id>', methods=['POST'])
@login_required
def delete(chatbot_id, doc_id):
    user_id = current_user.id
    # Delete from PostgreSQL
    g.cursor.execute("DELETE FROM document_mapping WHERE id = %s AND user_id = %s RETURNING filename;", (doc_id, user_id))
    result = g.cursor.fetchone()
    g.db_conn.commit()
    if result:
        filename = result[0]
        prefix = f"{filename}_"
        print(f"Deleted entry for ID {doc_id} from the database")

        namespace = f"{user_id}{chatbot_id}"
        list_url = f"https://{index_host}/vectors/list?namespace={namespace}&prefix={prefix}"
        delete_url = f"https://{index_host}/vectors/delete"

        headers = {
            "Api-Key": pinecone_api_key,
            "Content-Type": "application/json"
        }

        list_response = requests.get(list_url, headers=headers)
        if list_response.status_code == 200:
            ids_to_delete = [record['id'] for record in list_response.json().get('vectors', [])]
            if ids_to_delete:
                delete_response = requests.post(delete_url, headers=headers, json={"ids": ids_to_delete})
                if delete_response.status_code == 200:
                    print(f"Deleted vectors with IDS {ids_to_delete} from Pinecone")
        else:
            print(f"Error listing record from Pincone")
    else:
        print(f"File not found")

    return redirect(url_for('admin', chatbot_id=chatbot_id))

@app.route('/<int:chatbot_id>/settings')
@login_required
def settings(chatbot_id):
    user_id = current_user.id
    g.cursor.execute("SELECT widget_icon_url, background_color, font_style, bot_temperature, greeting_message, custom_prompt, dot_color, logo, chatbot_title, title_color, border_color,primary_color,secondary_color,suggested_questions FROM chatbot_settings WHERE user_id = %s AND id = %s;", (user_id, chatbot_id,))
    row = g.cursor.fetchone()

    # It is assumed that row will not be None, as default settings should have been set in the /admin route.
    settings = {
        'widget_icon': row[0],
        'background_color': row[1],
        'font_style': row[2],
        'bot_temperature': row[3],
        'greeting_message': row[4],
        'custom_prompt': row[5],
        'dot_color': row[6],
        'logo': row[7],
        'chatbot_title': row[8],
        'title_color': row[9],
        'border_color': row[10],
        'primary_color': row[11],
        'secondary_color': row[12],
        'suggested_questions': row[13],
        
    }

    return render_template('settings.html', settings=settings, user_id=user_id, chatbot_id=chatbot_id)

def update_chatbot_settings_in_db(chatbot_id, widget_icon, background_color, font_style, bot_temperature, greeting_message, custom_prompt,dot_color,logo,chatbot_title,title_color,border_color,primary_color,secondary_color,suggested_questions):
    user_id = current_user.id
    sql = """
    UPDATE chatbot_settings
    SET widget_icon_url = %s, background_color = %s, font_style = %s, bot_temperature = %s, greeting_message = %s, custom_prompt = %s, dot_color = %s, logo = %s, chatbot_title = %s, title_color = %s, border_color = %s, primary_color = %s, secondary_color = %s, suggested_questions = %s WHERE user_id = %s AND id = %s;
    """

    g.cursor.execute(sql, (widget_icon, background_color, font_style, bot_temperature, greeting_message, custom_prompt, dot_color,logo,chatbot_title,title_color,border_color,primary_color,secondary_color,suggested_questions, user_id, chatbot_id)) 
    g.db_conn.commit()

@app.route('/<int:chatbot_id>/update_chatbot_settings', methods=['POST'])
def update_chatbot_settings(chatbot_id):
    widget_icon = "ecco_icon"
    background_color = request.form.get('background_color')
    font_style = request.form.get('font_style')
    bot_temperature = request.form.get('bot_temperature')
    greeting_message = request.form.get('greeting_message')
    custom_prompt = request.form.get('custom_prompt')
    dot_color = request.form.get('dot_color')
    logo = request.form.get('logo')
    chatbot_title = request.form.get('chatbot_title')
    title_color = request.form.get('title_color')
    border_color = request.form.get('border_color')
    primary_color = request.form.get('primary')
    secondary_color = request.form.get('secondary')
    suggested_questions = request.form.get('suggested_questions')
    suggested_questions = suggested_questions.split('\n')


    update_chatbot_settings_in_db(chatbot_id, widget_icon, background_color, font_style, bot_temperature, greeting_message, custom_prompt,dot_color,logo,chatbot_title,title_color,border_color,primary_color,secondary_color,suggested_questions)

    flash('Chatbot settings updated successfully!', 'success')
    return redirect(url_for('settings', chatbot_id=chatbot_id))

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() == 'png'

@app.route('/<int:chatbot_id>/upload_logo', methods=['POST'])
def upload_logo(chatbot_id):
    user_id = current_user.id
    print(user_id, chatbot_id)
    if 'logo' not in request.files:
        flash('No file part')
        return redirect(request.url)
    file = request.files['logo']
    if file.filename == '':
        flash('No selected file')
        return redirect(request.url)
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)

        # Create a blob client using the local file name as the name for the blob
        blob_service_client = BlobServiceClient.from_connection_string(connection_string)
        blob_client = blob_service_client.get_blob_client(container_name, filename)

        # Upload the file
        blob_client.upload_blob(file, blob_type="BlockBlob", content_settings=ContentSettings(content_type='image/png', content_disposition='inline'))

        # Save the URL of the blob
        logo_url = blob_client.url
        print(logo_url)
        g.cursor.execute("UPDATE chatbot_settings SET logo = %s WHERE user_id = %s AND id = %s;", (logo_url, user_id, chatbot_id))
        g.db_conn.commit()  
        # Now you can save logo_url in your PostgreSQL database

        return redirect(url_for('settings', chatbot_id=chatbot_id))

@app.route('/<int:user_id>/<int:chatbot_id>/greeting_message')
def greeting_message(user_id, chatbot_id):
    # Query PostgreSQL to get the greeting message for the user with id = 1
    g.cursor.execute("SELECT greeting_message FROM chatbot_settings WHERE user_id = %s AND id = %s;", (user_id, chatbot_id))
    row = g.cursor.fetchone()
    if row is None:
        greeting_message = 'Hello, how can I help?'  # Default value if no greeting message is found for the user
    else:
        greeting_message = row[0]
    return jsonify(greeting_message=greeting_message)

@app.route('/<int:chatbot_id>/analytics')
@login_required
def analytics(chatbot_id):
    user_id = current_user.id
    g.cursor.execute("SELECT user_question, bot_response, feedback_type FROM feedback WHERE user_id = %s AND chatbot_id = %s;", (user_id, chatbot_id))
    rows = g.cursor.fetchall()

    if not rows:
        return render_template('analytics.html', data=[], common_topics=None)

    questions = [row[0] for row in rows]

    # Use TfidfVectorizer to convert text data to a matrix of TF-IDF features
    vectorizer = TfidfVectorizer(stop_words='english')
    X = vectorizer.fit_transform(questions)

    common_topics = []
    if X.shape[1] > 3:  # Check if there are more than 3 features
        # Use TruncatedSVD for dimensionality reduction
        svd = TruncatedSVD(n_components=3)
        normalizer = Normalizer(copy=False)
        lsa = make_pipeline(svd, normalizer)

        X_lsa = lsa.fit_transform(X)

        # Apply KMeans clustering to find topics
        num_clusters = 3
        kmeans = KMeans(n_clusters=num_clusters, random_state=42)
        kmeans.fit(X_lsa)

        # Get the top terms for each cluster
        terms = vectorizer.get_feature_names_out()
        original_space_centroids = svd.inverse_transform(kmeans.cluster_centers_)
        order_centroids = original_space_centroids.argsort()[:, ::-1]

        seen = set()

        for i in range(num_clusters):
            for ind in order_centroids[i, :5]:  # Choose top 5 terms per cluster
                term = terms[ind]
                if term not in seen:
                    # Count how many questions contain the term
                    term_count = sum(1 for question in questions if term in question)
                    if term_count >= 2:
                        common_topics.append(term)
                    seen.add(term)

    data = []
    if rows:
        for row in rows:
            data.append({
                'user_question': row[0],
                'bot_response': row[1],
                'feedback_type': row[2]
            })
    else:
        data = []

    return render_template('analytics.html', data=data, common_topics=common_topics, chatbot_id=chatbot_id)


#!!!!!!!!!!!!!!!!!!!!
#route not being used
#!!!!!!!!!!!!!!!!!!!!
@app.route('/delete_feedback', methods=['POST'])
@login_required
def delete_feedback():
    user_id = current_user.id
    user_question = request.form.get('user_question')
    bot_response = request.form.get('bot_response')

    g.cursor.execute("DELETE FROM feedback WHERE user_id = %s AND user_question = %s AND bot_response = %s;", (user_id, user_question, bot_response))
    g.conn.commit()

    flash('Feedback successfully deleted', 'success')

    return redirect(url_for('analytics'))

#!!!!!!!!!!!!!!!!!!!!
#route not being used
#!!!!!!!!!!!!!!!!!!!!
@app.route('/analytics/data')
@login_required
def analytics_data():
    user_id = current_user.id
    # Fetch the number of likes from the database
    g.cursor.execute("SELECT COUNT(*) FROM feedback WHERE feedback_type = 'Like' AND user_id = %s;", (user_id,))
    likes = g.cursor.fetchone()[0]

    # Fetch the number of dislikes from the database
    g.cursor.execute("SELECT COUNT(*) FROM feedback WHERE feedback_type = 'Dislike' AND user_id = %s;", (user_id,))
    dislikes = g.cursor.fetchone()[0]

    # Fetch the number of none feedback from the database
    g.cursor.execute("SELECT COUNT(*) FROM feedback WHERE feedback_type IS NULL AND user_id = %s;", (user_id,))
    none = g.cursor.fetchone()[0]

    # Return the data as JSON
    return jsonify({'likes': likes, 'dislikes': dislikes, 'none': none})

@app.errorhandler(404)
def page_not_found(e):
    # note that we set the 404 status explicitly
    return render_template('error.html', message="Page not found."), 404

@app.errorhandler(500)
def internal_server_error(e):
    # note that we set the 500 status explicitly
    return render_template('error.html', message="An unexpected error has occurred. Please try again later."), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))  # Use PORT if it's there
    app.run(host='0.0.0.0', port=port, debug=False)  # Set host to '0.0.0.0'