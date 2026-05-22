from .models import CustomUser, Profile, CollectedData, Transaction, ReferralBonus, Network, Data_price
from datetime import datetime
from django.utils import timezone
def transact_failed_count(Transaction):
    trans = Transaction.objects.filter(status="failed").count()
    return trans

def total_transact_success_today(Transaction):
    date=timezone.now().date()
    trans = Transaction.objects.filter(status="success")
    all_list=[]
    for i in trans:
        if i.created_at.date() == date:
            all_list.append(i.amount)
    total_amount=sum(all_list)
    return total_amount
def total_transact_success(Transaction):
    trans = Transaction.objects.filter(status="success")
    all_list=[]
    for i in trans:
            all_list.append(i.amount)
    total_amount=sum(all_list)
    return total_amount
def user_count(CustomUser):
    trans = CustomUser.objects.all().count()
    return trans
def active_user():
    user=CustomUser.objects.filter(is_active=True).count()
    return user
class sales:
    def Airtime_sale():
         trans = Transaction.objects.filter(service="airtime")
         all_list=[]
         for i in trans:
            all_list.append(i.amount)
         total_amount=sum(all_list)
         return total_amount
        
    def data_sale():
         trans = Transaction.objects.filter(service="data")
         all_list=[]
         for i in trans:
            all_list.append(i.amount)
         total_amount=sum(all_list)
         return total_amount
        
    def Cable_sale():
        trans = Transaction.objects.filter(service="cable")
        all_list=[]
        for i in trans:
            all_list.append(i.amount)
        total_amount=sum(all_list)
        return total_amount
    def percentage_cal_data():
         trans_data= Transaction.objects.filter(service="data").count()
         trans_airtime = Transaction.objects.filter(service="airtime").count()
         trans_cable = Transaction.objects.filter(service="cable").count()
         total=trans_data + trans_airtime + trans_cable
         data_pecentage=int(trans_data/total * 100)
         return data_pecentage
     
     
    def percentage_cal_airtime():
         trans_data= Transaction.objects.filter(service="data").count()
         trans_airtime = Transaction.objects.filter(service="airtime").count()
         trans_cable = Transaction.objects.filter(service="cable").count()
         total=trans_data + trans_airtime + trans_cable
         airtime_pecentage=int(trans_airtime/total * 100)
         return airtime_pecentage
     
    def percentage_cal_cable():
         trans_data= Transaction.objects.filter(service="data").count()
         trans_airtime = Transaction.objects.filter(service="airtime").count()
         trans_cable = Transaction.objects.filter(service="cable").count()
         total=trans_data + trans_airtime + trans_cable
         cable_pecentage=int(trans_cable/total * 100)
         return cable_pecentage
     
    def get_data_plan(network):
         url="https://smeplug.ng/api/v1/data/plans"
         header={
            "Authorization": "Bearer 900fd38e4873cdf10f501db5ca4bc95c0984f559bf89706ce52513123a6cf6a4"
            }
         res=requests.get(url,headers=header)
         info_res=res.json()
         check= info_res["data"][network]
         for i in check:
           get_info=(i["id"])
         return get_info
        
         
            