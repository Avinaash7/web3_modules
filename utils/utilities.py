from web3 import Web3
#from transaction.models import BalanceSnapshot
from decimal import Decimal
import time
import random

from loguru import logger as LOGGER


class Receipt:

    def __init__(self, receipt):
        self.receipt = receipt

    def get_receipt_status(self):
        #print(f"self.receipt: {self.receipt}")
        receipt_status = self.receipt.get("status")
        LOGGER.info(f"[get_receipt_status] Status: {receipt_status}")
        if receipt_status == 1:
            return True
        else:
            return False

    def calculate_gas_used(self):
        '''takes receipt
        returns gas used in ether
        '''
        effective_gas_price = self.receipt.get('effectiveGasPrice')
        if effective_gas_price < 1:
            effective_gas_price = 250000000
        gas_used = self.receipt['gasUsed']
        cost_of_gas = effective_gas_price * gas_used
        cost_of_gas = Web3.from_wei(cost_of_gas, 'ether')
        return cost_of_gas


def write_swap_to_db(account, sell_coin, sell_amt, buy_amt, buy_coin ,tx_id, platform, snapshot=None, receipt=None):
    """writes swap tx to SwapTransaction and Transaction Table

    Args:
        account (_type_):
        sell_coin (_type_):
        buy_coin (_type_):
        sell_amt (_type_):
        tx_id (_type_):
        platform (_type_): text of the platform.  ie 'SYNCSWAP'
    """
    from utils.utilities import Receipt
    from transaction.models import Transaction, SwapTransaction
    # can't decode ERC20 transfers and gas refunds...
    # account.get_transaction(tx_id)

    swap_tx = SwapTransaction.objects.create(
        platform=platform,
        sell_amt=sell_amt,
        sell_token=sell_coin,
        buy_amt=buy_amt,
        buy_token=buy_coin,
        fees_paid=None,
        account=account,
        balance_snapshot=snapshot
    )
    tx = Transaction.objects.create(
        action_type='TRADE',
        account=account,
        txid=tx_id,
        fees_paid=None,
        chain = 'ZKSYNC',
        swap_tx = swap_tx,
        receipt = receipt
    )

    #save the swap_tx to the transaction
    swap_tx.tx = tx
    swap_tx.save()

    LOGGER.debug(f"Recorded {platform} transaction into db")

    # except Exception as e:
    #     LOGGER.error(f"Error writing swap to db: {e}")
        #import pdb; pdb.set_trace()
def determine_decimals(buy_token, sell_token, coin_data):

    try:
        sell_token_decimals = coin_data[sell_token]['tokenDecimals']
        buy_token_decimals = coin_data[buy_token]['tokenDecimals']
    except KeyError:
        raise ValueError(f"One or both tokens ({buy_token}, {sell_token}) not found in coin_data.")

    return buy_token_decimals, sell_token_decimals

def get_amount(
            sell_token,
            amount,
            sell_token_decimals
    ):
        """returns wei for eth or amount *10**decimals for alts

        Returns:
            amount_parsed: int to pass as amountIn for swap
        """

        sell_token_decimals = int(sell_token_decimals)
        if sell_token == "ETH":
            amount_parsed = Web3.to_wei(amount, "ether")

        else:
            amount_parsed = int(Decimal(amount) * (10 ** sell_token_decimals))

        return amount_parsed

def check_and_compare_balance():
    pass

def get_swap_deadline():
    deadline_options = [300, 600, 900, 1200]
    deadline = int(time.time()) + random.choice(deadline_options)
    return deadline
