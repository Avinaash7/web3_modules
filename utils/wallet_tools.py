import os
import sys
import time

# Add the parent directory to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from web3 import Web3
from web3.exceptions import TransactionNotFound
from time import sleep
from config import ERC20_ABI, ZKSYNC_TOKENS
from random import randint
from eth_account import Account as EthAccount

from loguru import logger as LOGGER
GAS_MULTIPLIER = 1

class WalletTool:
    _rpc_url = None

    def __init__(self, privkey):
        self.decr_privkey = privkey
        self.pubkey = self.get_pubkey()
        self.id = 'id placeholder'  #ignore this
        WalletTool._rpc_url = 'https://zksync.meowrpc.com'#get_random_rpc()[0]
        #use same rpc for all calls within an init
      #  if not WalletTool._rpc_url:
       #     WalletTool._rpc_url = 'https://zksync.meowrpc.com'#get_random_rpc()[0]
        self.w3 = Web3(Web3.HTTPProvider(WalletTool._rpc_url))
        self.checksum_address = self.w3.to_checksum_address(self.pubkey)
        

    def get_nonce(self, chain):
        if chain == 'ZK':
            nonce = self.w3.eth.get_transaction_count(self.checksum_address)
            # LOGGER.info(f'Nonce updated to {nonce}')
            return nonce
        LOGGER.error(f'{chain} not found!')
        import pdb; pdb.set_trace()

    def get_pubkey(self):
        acct = EthAccount.from_key(self.decr_privkey)
        return acct.address
    
    def check_allowance(self, token_address: str, contract_address: str) -> float:
        try:
            token_address = Web3.to_checksum_address(token_address)
            contract_address = Web3.to_checksum_address(contract_address)

            contract = self.w3.eth.contract(address=token_address, abi=ERC20_ABI)
            amount_approved = contract.functions.allowance(self.checksum_address, contract_address).call()

        except:
            LOGGER.error(f"Error checking allowance...")
            return False

        return amount_approved

    def approve(self, amount: float, token_address: str, contract_address: str):
        try:

            token_address = Web3.to_checksum_address(token_address)
            contract_address = Web3.to_checksum_address(contract_address)

            contract = self.w3.eth.contract(address=token_address, abi=ERC20_ABI)

            allowance_amount = self.check_allowance(token_address, contract_address)

            if amount > allowance_amount or amount == 0:
                LOGGER.warning(f" Amount not approved: [PK: {self.id}][{self.pubkey}] ")

                approve_amount = 115792089237316195423570985008687907853269984665640564039457584007913129639935

                tx = {
                    "chainId": self.w3.eth.chain_id,
                    "from": self.checksum_address,
                    "nonce": self.w3.eth.get_transaction_count(self.checksum_address),
                    "gasPrice": self.w3.eth.gas_price
                }

                LOGGER.info(f'Approving default max amount for token: {token_address} to contract: {contract_address}')

                transaction = contract.functions.approve(
                    contract_address,
                    approve_amount
                ).build_transaction(tx)

                signed_txn = self.sign(transaction)

                txn_hash = self.send_raw_transaction(signed_txn)

                self.wait_until_tx_finished(txn_hash.hex())

                random_sleep = randint(3, 7)
                LOGGER.success(f'Token spend approval successful. Sleeping for {random_sleep} seconds')
                sleep(random_sleep)
                return True
            
        except:
            LOGGER.error(f"Error running Approve...")
            import pdb; pdb.set_trace()
    #         return False


    def get_contract(self, address, abi):
        #import pdb; pdb.set_trace()
        return self.w3.eth.contract(address=address, abi=abi)


    def print_pubkey(self):
        print(self.pubkey)

    def sign(self, transaction):
        gas = self.w3.eth.estimate_gas(transaction)
        gas = int(gas * GAS_MULTIPLIER)

        transaction.update({"gas": gas})

        signed_txn = self.w3.eth.account.sign_transaction(transaction, self.decr_privkey)

        return signed_txn

    def send_raw_transaction(self, signed_txn):
        try:
            

            for _ in range (5):
                try:
                    txn_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
                    sleep(1)
                    break

                except Exception as e:
                    error_msg = str(e)
                    if "insufficient funds" in error_msg:
                        LOGGER.error(f"Insufficient funds for {self.pubkey}. Maybe we need to update balances first?")
                        acc.update_zk_all_balance()
                        txn_hash = 0
                        #is returning the txn hash a good way to get out of it, or should it return false?
                        return txn_hash
                    
                    if 'Read timed out' in error_msg:
                        pass

                    LOGGER.error(f"error sending transaction! {error_msg}")
                    #txn_hash = None
                    import pdb; pdb.set_trace()

            return txn_hash

        except:
            LOGGER.error(f"Error sending raw transactions")
            return False

    def wait_until_tx_finished(self, hash: str, max_wait_time=180):
        start_time = time.time()
        LOGGER.info(f"[wait_until_tx_finished] Looking for tx receipt..")
        sleep(5)
        MAX_RETRIES = 30  # Number of retries for exceptions

        for _ in range(MAX_RETRIES):
            try:
                receipts = self.w3.eth.get_transaction_receipt(hash)
                status = receipts.get("status")

                attempts = 0
                rpc_switches = 0
                while attempts < 3:
                    if status == 1:
                        LOGGER.success(f"==> [PK: {self.id}][{self.pubkey}] txid: {hash} successful!")
                        return receipts

                    elif status is None:
                        LOGGER.info(f'tx not found. waiting 1s')
                        sleep(2)
                        attempts += 1
                        continue

                    if attempts == 6:
                        LOGGER.info(f"==> tx failed after 3 attempts, new rpc time")
                        WalletTool._rpc_url = 'https://zksync.meowrpc.com'#get_random_rpc()[0]
                        self.w3 = Web3(Web3.HTTPProvider(WalletTool._rpc_url))
                        attempts = 0
                        rpc_switches += 1
                        continue

                    if rpc_switches == 2:
                        LOGGER.error(f"==> tx failed after 2 rpc switches. exiting")
                        return receipts

                else:
                    LOGGER.error(f"==> [PK: {self.id}][{self.pubkey}] {hash} maybe failed, who knows.")
                    return False

            except Exception as e:
                LOGGER.warning(f"Error getting transaction receipt: {e}.")
                sleep(2)
        else:
            LOGGER.error(f"Exhausted all retries. Error getting transaction receipt: {e}")
            return False



if __name__ == '__main__':
    with open('privkey.txt','r') as f:
        privkey = f.read()

    test_class = WalletTool(privkey)
    print(test_class.get_nonce('ZK'))

