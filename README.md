

# Quickstart Guide


<br>


## Preliminary checks

### Step 0: Requirements

1. **Git**
2. **Azure account with active subscription**

3. **Frontend**  : Node installed
4. **Backend**   : Python 3.13.2 or higher

### Step 1: Downloading the repository
```bash
git clone https://github.com/K3YB04RD-w4rri0r/edge-chatbot.git
cd edge-chatbot
```


<br><br>




## Setting up the backend
### Step 1: Environment and Requirements

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate

# requirements
pip install -r requirements.txt

cp .env.example .env 
```

### Step 2: Azure Services
For the backend we use:
1. **Azure Redis Cache** : For authentification and possibly caching in the future
2. **Azure Blob Storage**: File storage service for our conversation attachments
3. **Postgres Server and Databases**: SQL databases to store users, messages and attachments.

### Step 3: Setting the .env


**open the .env file to edit**
```bash
nano .env
```

<br>

For the full guide on how to set it up, go to: 
 
        https://docs.google.com/document/d/1aj6Xde738f11dvOPOEINZlTvOnQyM29CmLY5AadRxbc/edit?usp=sharing 


### Step 4: OpenAI keys

1. Azure OpenAi for chatgpt
2. Normal Google key for Gemini

### Step 5: Initializations

Initialize the sql databases with the init_db script
```bash
mv scripts/init_db.py .

python3 init_db.py --recreate

mv init_db.py scripts/init_db.py
```

### Step 6: Running the app

```bash

python3 main.py

```


<br><br>




## Setting up the frontend

Open a new Terminal

### Step 1: Creating the React App

```bash
npx create-react-app test_frontend # or name_of_frontend_folder
cd test_frontend

# Required dependencies
npm install lucide-react
```

#### Note:  if you changed the name, make sure to modify any references to package.json and package-lock.json by the new app name in the future


### Step 2: Environment Configuration

Since you should be at the root of the frontend, you can now create a .env file. 

```bash
nano .env
# or directly run
#cp ../frontend-resources/development_frontend/.env.example .env
```

And Copy Paste the following content

```env
REACT_APP_API_BASE_URL=http://localhost:8000   # backend adress
REACT_APP_MAX_FILE_SIZE=10485760               # Max size upload for files
```

Then Save and Exit (ctrl S + ctrl X)

### Step 3: Adding the code

Now we have to add the React Components for our Code from frontend-resources. 
In  the following commands we will assume that you haven't changed directories and are still in the test_frontend (or the name you chose).
We will also set up the development environment instead of production.

1. **package.json and package-lock.json**     -> Replace the newly created package.json in your frontend with ours.

        
        cp ../frontend-resources/development_frontend/package.json package.json

        cp ../frontend-resources/development_frontend/package-lock.json package-lock.json
        

2. **Components and Services folder**     -> These act as the components for the frontend as well as background tasks such as checking tokens. 
        
        # Components folder
        cp -r ../frontend-resources/development_frontend/src/components src/components

        # Services folder
        cp -r ../frontend-resources/development_frontend/src/services src/services
       
3. **Replacing index.html**v -> html landing page which holds the whole app together.

        cp -r ../frontend-resources/development_frontend/public/index.html public/index.html
        
4. **Finalizing the App**     -> Replace the core App.js and App.cs files for the frontend.
        
        # App.css
        cp ../frontend-resources/development_frontend/src/App.css src/App.css

        # App.css
        cp ../frontend-resources/development_frontend/src/App.js src/App.js

## Step 4: Running the frontend

```bash
npm install # ONLY the very first time you deploy the app
npm start
```

The browser should open automatically to http://localhost:3000 and the App should be displayed. 
Make sure the backend is up and running before hand. 
