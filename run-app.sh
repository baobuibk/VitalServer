#!/bin/bash

# Run the frontend script in the background
python3 FrontEnd/main.py &

# Run the backend script in the background
python3 BackEnd/main.py &

# Wait for all background processes to complete
wait
