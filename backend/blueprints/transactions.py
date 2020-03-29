import json
from uuid import uuid4

import requests
from flask import Blueprint, make_response, jsonify, request

import backend as node
from backend.utils import required_fields, validate_transaction_document

from backend.blockchain import \
    Transaction, TransactionInput, TransactionOutput, Wallet, verify_signature


bp = Blueprint('transactions', __name__, url_prefix='/transactions')


@bp.route('/generate_wallet', methods=['GET'])
def generate_wallet():
    """
    Generate a wallet, add it to the node and return the keys to the user.
    """
    node.wallet = Wallet()

    response = {
        'private_key': node.wallet.private_key,
        'public_key': node.wallet.public_key
    }

    return make_response(jsonify(response)), 200


@bp.route('/create', methods=['POST'])
@required_fields('sender_address', 'recipient_address', 'amount')
def create_transaction():
    """
    Create a valid transaction document using any UTXOs available and return it.
    """
    data = request.get_json()
    response = {}
    status_code = None

    if node.wallet.balance() < data['amount']:
        response = dict(message='Your balance is not enough to complete transaction')
        status_code = 400

        return make_response(jsonify(response)), status_code

    # TODO: What if recipient doesn't exist, amount is negative etc.?

    transaction_id = str(uuid4())

    # Use as many utxos as necessary to create the new transaction inputs
    sender_address = data['sender_address']
    sum_ = 0
    tx_inputs = []
    while sum_ < data['amount']:
        utxo = node.utxos[sender_address].pop()
        sum_ += utxo.amount()
        tx_inputs.append(TransactionInput(previous_output_id=utxo.id, amount=utxo.amount))

    # Create 2 transaction outputs, one for the transfer and one for the sender's change
    tx_outputs = [
        TransactionOutput(
            transaction_id=transaction_id,
            recipient_address=data['recipient_address'],
            amount=data['amount']
        ),
        TransactionOutput(
            transaction_id=transaction_id,
            recipient_address=data['sender_address'],
            amount=sum_ - data['amount']
        )
    ]

    # Actual transaction object:
    tx = Transaction(
        sender_address=data['sender_address'],
        recipient_address=data['recipient_address'],
        amount=data['amount'],
        transaction_inputs=tx_inputs,
        transaction_outputs=tx_outputs,
        id=transaction_id
    )

    response = tx.to_dict()
    return make_response(jsonify(response)), 200


@bp.route('/sign', methods=['POST'])
def sign_transaction():
    """
    Sign provided transaction document using host private key.
    """
    data = request.get_json()

    try:
        tx = Transaction.from_dict(data)
    except TypeError:
        response = dict(message='Improper transaction json provided.')
        status_code = 400
        return make_response(jsonify(response)), status_code

    signature = tx.sign(node.wallet.private_key_rsa)
    response = dict(signature=signature)
    return make_response(jsonify(response)), 200


@bp.route('/submit', methods=['POST'])
@required_fields('transaction', 'signature')
def submit_transaction():
    """
    Parse a signed transaction document, check its validity, verify signature and add to local blockchain.
    Broadcast to the same endpoint for peers if required.
    """
    data = request.get_json()

    # Create candidate transaction object
    try:
        tx = Transaction.from_dict(data['transaction'])
    except (KeyError, TypeError):
        response = dict(message='Improper transaction json provided.')
        status_code = 400
        return make_response(jsonify(response)), status_code

    # Validate transaction as-is
    val_result = validate_transaction_document(tx)
    if isinstance(val_result, str):
        response = dict(message=val_result)
        status_code = 400
        return make_response(jsonify(response)), status_code

    # Verify signature
    sign_result = verify_signature(tx, data['signature'])
    if isinstance(sign_result, str):
        response = dict(message=sign_result)
        status_code = 400
        return make_response(jsonify(response)), status_code

    # Add transactions to local blockchain and outputs to local UTXO archive
    node.blockchain.add_transaction(tx)
    for to in tx.transaction_outputs:
        node.utxos[to.recipient_address].append(to)

    # Broadcast if needed and turn off broadcasting for other nodes
    if request.args.get('broadcast', type=int, default=0):
        for address in node.peers:
            requests.post(
                address + '/submit?broadcast=0',
                data=json.dumps(data['transaction']),
                content_type='application/json'
            )

    response = dict(message='Transaction added.')
    return make_response(jsonify(response)), 200