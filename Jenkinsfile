// ==============================================================================
// StockkAsk CI/CD Declarative Jenkins Pipeline (Jenkinsfile)
// ==============================================================================
// WHAT IS A JENKINSFILE?
// A Jenkinsfile is a text file that contains the definition of a Jenkins Pipeline.
// It defines the automation workflow for building, testing, scanning, and deploying 
// your application. Writing it in a file allows you to store your build pipeline 
// in Git (Pipeline-as-Code).
//
// WHAT IS A "PIPELINE"?
// A pipeline is a sequence of tasks (called "stages") that your code goes through 
// from your computer to production.
//
// WHAT IS A "STAGE"?
// A stage is a block containing one or more "steps". It represents a logical phase 
// of the build process (e.g., "Build", "Test", "Deploy"). If any stage fails, the 
// entire pipeline stops, notifying you of the failure.
// ==============================================================================

pipeline {
    // 'agent' tells Jenkins WHERE to run this pipeline. 
    // 'any' means Jenkins can run it on any available build computer (executor node).
    agent any

    // 'environment' blocks define global variables. 
    // Environment variables are key-value pairs that can be read by any stage 
    // in the pipeline (like global variables in Python).
    environment {
        // Name of our Docker image. We use the Jenkins build number to make it unique.
        DOCKER_IMAGE   = "stockkbot-backend"
        DOCKER_TAG     = "${env.BUILD_NUMBER}"
        REGISTRY_CREDS = "docker-registry-credentials" // Credential ID stored in Jenkins
        IMAGE_NAME     = "stockk.trade/stockkbot-backend"
        
        // Environment configurations for our tests
        APP_ENV        = "testing"
    }

    stages {
        // ----------------------------------------------------------------------
        // STAGE 1: CHECKOUT
        // ----------------------------------------------------------------------
        // Downloads your source code from your Git repository (like GitHub or GitLab) 
        // to the Jenkins build runner workspace.
        stage('Checkout Source Code') {
            steps {
                echo 'Checking out code from Git...'
                // 'checkout scm' automatically pulls the exact commit that triggered this build.
                checkout scm
            }
        }

        // ----------------------------------------------------------------------
        // STAGE 2: SECURITY & LINTING
        // ----------------------------------------------------------------------
        // Before running the application, we check the code quality (Linting) 
        // and scan for vulnerabilities or accidentally committed secrets (like API keys).
        // To avoid needing Python installed on the host, we run the tools in a temporary container.
        stage('Security Scanning & Linting') {
            steps {
                echo 'Running Python syntax checks and security scan in Docker...'
                
                // Run a temporary Python container, mount the workspace, and execute flake8 and bandit.
                bat 'docker run --rm -v "%WORKSPACE%:/app" python:3.12-slim sh -c "pip install --no-cache-dir flake8 bandit && flake8 /app/backend/ --count --select=E9,F63,F7,F82 --show-source --statistics && bandit -r /app/backend/ -ll"'
            }
        }

        // ----------------------------------------------------------------------
        // STAGE 3: BUILD DOCKER IMAGE
        // ----------------------------------------------------------------------
        // Builds the secure, multi-stage Docker image using the Dockerfile 
        // we wrote in the backend folder.
        stage('Build Docker Image') {
            steps {
                echo "Building Docker image: ${DOCKER_IMAGE}:${DOCKER_TAG}..."
                
                // Build the Docker image from our backend context.
                // We tag it with the Jenkins build number for absolute version tracking.
                bat "docker build -t ${DOCKER_IMAGE}:${DOCKER_TAG} ./backend"
            }
        }

        // ----------------------------------------------------------------------
        // STAGE 4: AUTOMATED COMPLIANCE & UNIT TESTING
        // ----------------------------------------------------------------------
        // Runs our automated tests inside the freshly built Docker container.
        // This validates that our RAG service blocks prompt injections and maintains
        // strict SEBI rules before we release the image to public servers.
        //
        // HOW JENKINS SECURELY INJECTS SECRETS:
        // We use the 'withCredentials' block. Jenkins retrieves these secrets from 
        // its encrypted database. Inside this block, the secrets are injected as temporary 
        // environment variables. Jenkins will AUTOMATICALLY mask these variables in 
        // the console logs (replacing them with ****) so they are never exposed!
        stage('Automated Compliance & Security Testing') {
            steps {
                echo 'Running automated SEBI Compliance and Security Injection tests...'
                
                // Retrieve the OpenAI, Groq, or Pinecone API keys securely from Jenkins credentials
                // and inject them as environment variables during test execution.
                withCredentials([
                    string(credentialsId: 'openai-api-key', variable: 'OPENAI_API_KEY'),
                    string(credentialsId: 'groq-api-key', variable: 'GROQ_API_KEY'),
                    string(credentialsId: 'pinecone-api-key', variable: 'PINECONE_API_KEY')
                ]) {
                    // To run the tests, we run a temporary Docker container from our built image.
                    // We mount the workspace 'tests' directory into the container using ${WORKSPACE}.
                    // We pass the API keys securely via environment variables (-e).
                    bat """
                        docker run --rm -v "${WORKSPACE}/tests:/app/tests" -e OPENAI_API_KEY="${OPENAI_API_KEY}" -e GROQ_API_KEY="${GROQ_API_KEY}" -e PINECONE_API_KEY="${PINECONE_API_KEY}" -e APP_ENV="${APP_ENV}" ${DOCKER_IMAGE}:${DOCKER_TAG} python -m unittest discover -s tests -p "test_*.py"
                    """
                }
            }
        }

        // ----------------------------------------------------------------------
        // ----------------------------------------------------------------------
        // STAGE 5: LOCAL DEPLOYMENT
        // ----------------------------------------------------------------------
        // If all stages pass, we boot the application containers locally using 
        // Docker Compose so the developer can access the running project.
        stage('Deploy Locally') {
            steps {
                echo 'Testing completed successfully. Starting local deployment...'
                
                // Since the .env file is gitignored, we dynamically generate a clean one 
                // in the Jenkins workspace using the secure credentials we injected.
                withCredentials([
                    string(credentialsId: 'openai-api-key', variable: 'OPENAI_API_KEY'),
                    string(credentialsId: 'groq-api-key', variable: 'GROQ_API_KEY'),
                    string(credentialsId: 'pinecone-api-key', variable: 'PINECONE_API_KEY')
                ]) {
                    bat """
                        @echo off
                        echo # Generated by Jenkins > backend\\.env
                        echo OPENAI_API_KEY=${OPENAI_API_KEY} >> backend\\.env
                        echo GROQ_API_KEY=${GROQ_API_KEY} >> backend\\.env
                        echo PINECONE_API_KEY=${PINECONE_API_KEY} >> backend\\.env
                        echo APP_ENV=production >> backend\\.env
                        echo ALLOWED_ORIGINS=https://stockk.trade,http://localhost:3000 >> backend\\.env
                        echo LOG_LEVEL=INFO >> backend\\.env
                        echo RATE_LIMIT_PER_MINUTE=20 >> backend\\.env
                        echo RATE_LIMIT_PER_DAY=500 >> backend\\.env
                        echo EMBEDDING_MODEL=text-embedding-3-small >> backend\\.env
                        echo CHAT_MODEL=gpt-4o-mini >> backend\\.env
                        echo TOP_K_RESULTS=5 >> backend\\.env
                        echo MAX_CONTEXT_TOKENS=2000 >> backend\\.env
                    """
                }
                
                // Stop and remove old backend and frontend containers if they are running
                bat 'docker stop stockkbot-api stockkbot-frontend || exit 0'
                bat 'docker rm stockkbot-api stockkbot-frontend || exit 0'
                
                // Deploy Backend: Run the container using our production settings from the Dockerfile (no reload crash!)
                bat "docker run -d --name stockkbot-api -p 8000:8000 --env-file backend\\.env ${DOCKER_IMAGE}:${DOCKER_TAG}"
                
                // Deploy Frontend: Start Nginx web server to serve the HTML pages
                bat 'docker run -d --name stockkbot-frontend -p 3000:80 -v "%WORKSPACE%/frontend:/usr/share/nginx/html" nginx:alpine'
                
                echo 'Local server deployed successfully! Access the web UI at http://localhost:3000/demo.html'
            }
        }
    }

    // 'post' block defines tasks that run after the pipeline completes.
    // This is perfect for notifications (email, Slack, Microsoft Teams).
    post {
        always {
            // Clean up workspace so we don't clog up Jenkins hard drives.
            cleanWs()
        }
        success {
            echo "Pipeline passed successfully! StockkAsk is safe, SEBI-compliant, and deployed."
        }
        failure {
            echo "Pipeline FAILED! Check logs above to identify which step (Lint, Build, or Test) failed."
        }
    }
}
