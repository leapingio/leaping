In root:
`pip install -r requirements.txt`\
`uvicorn backend.main:app `
NOTE: Please ensure that you're using `uvicorn[standard]` and not `uvicorn` since we've seen the latter result in some socket errors

In backend:
Please copy  `.env.example` to `.env` and ensure that all the variables in the `.env` file are set correctly.\
For the github token, please follow [these instructions](https://docs.github.com/en/github/authenticating-to-github/creating-a-personal-access-token) to create a token and set it in the `.env` file.


In a new terminal:\
`cd frontend`\
`npm run dev`

Frontend: http://localhost:5173

Stack trace to paste in:

Traceback (most recent call last):\
&nbsp;&nbsp;&nbsp;&nbsp;File "/Users/adrien/hndemo/backend/example.py", line 127, in <module>\
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;pay_for_day(emp_id, '2024-02-29')\
&nbsp;&nbsp;&nbsp;&nbsp;File "/Users/adrien/hndemo/backend/example.py", line 114, in pay_for_day\
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;if result.is_weekend:\
&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;^^^^^^^^^^^^^^^^^\
  AttributeError: 'NoneType' object has no attribute 'is_weekend'
