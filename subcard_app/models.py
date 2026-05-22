from email.policy import default
from django.db import models
from django.contrib.auth.models import AbstractUser
import uuid


class CustomUser(AbstractUser):
    phone = models.CharField(max_length=20, blank=True)
    wallet = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    referral_wallet = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    referral_code = models.CharField(max_length=150, unique=True, blank=True)
    referred_by = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="referrals",
    )
    is_email_verified = models.BooleanField(default=False)
    email_verification_token = models.UUIDField(default=uuid.uuid4, editable=False)
    email_verification_sent_at = models.DateTimeField(null=True, blank=True)
    transaction_pin = models.CharField(max_length=128, blank=True, null=True)

    def set_transaction_pin(self, pin):
        from django.contrib.auth.hashers import make_password
        self.transaction_pin = make_password(pin)
        self.save()

    def check_transaction_pin(self, pin):
        from django.contrib.auth.hashers import check_password
        if not self.transaction_pin:
            return False
        return check_password(pin, self.transaction_pin)


    def save(self, *args, **kwargs):
        if not self.referral_code:
            self.referral_code = self.username
        super().save(*args, **kwargs)

    def __str__(self):
        return self.username


class Withdrawal(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="withdrawals")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    payout_method = models.CharField(max_length=50, blank=True)
    bank_name = models.CharField(max_length=100, blank=True)
    account_number = models.CharField(max_length=50, blank=True)
    account_name = models.CharField(max_length=100, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)
    network = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - ₦{self.amount} ({self.status})"


class Profile(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    phone = models.CharField(max_length=20)
    wallet = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)

    # Katpay virtual account fields
    katpay_customer_id = models.CharField(max_length=100, blank=True)
    virtual_account_number = models.CharField(max_length=20, blank=True)
    virtual_account_bank = models.CharField(max_length=100, blank=True)
    virtual_account_reference = models.CharField(max_length=100, blank=True)
    virtual_account_status = models.CharField(max_length=20, blank=True)
    bvn = models.CharField(max_length=11, blank=True)
    nin = models.CharField(max_length=11, blank=True)

    def has_virtual_account(self):
        return bool(self.virtual_account_number and self.virtual_account_status == 'active')

    def __str__(self):
        return self.user.username


class CollectedData(models.Model):
    user = models.OneToOneField(CustomUser, on_delete=models.CASCADE)
    full_name = models.CharField(max_length=100, blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=50, blank=True)
    state = models.CharField(max_length=50, blank=True)
    country = models.CharField(max_length=50, blank=True)

    def __str__(self):
        return self.full_name or self.user.username


class Transaction(models.Model):
    SERVICE_CHOICES = [
        ("airtime", "Airtime"),
        ("data", "Data"),
        ("cable", "Cable TV"),
        ("electricity", "Electricity"),
        ("exam_pin", "Exam Pin"),
        ("bulk_sms", "Bulk SMS"),
        ("wallet_funding", "Wallet Funding"),
    ]

    user = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="transactions"
    )
    service = models.CharField(max_length=20, choices=SERVICE_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    description = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=20, default="pending")
    network_id = models.PositiveSmallIntegerField(null=True, blank=True)
    phone = models.CharField(max_length=15, blank=True)
    plan_id = models.CharField(max_length=50, blank=True)
    reference = models.CharField(max_length=100, blank=True)
    customer_reference = models.CharField(max_length=100, blank=True)
    api_response = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - {self.service} - ₦{self.amount}"


class ReferralBonus(models.Model):
    beneficiary = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="referral_earnings"
    )
    source_user = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="bonus_generated"
    )
    transaction = models.ForeignKey(
        Transaction, on_delete=models.CASCADE, related_name="bonuses"
    )
    level = models.PositiveSmallIntegerField()  # 1 = direct (20%), 2 = indirect (5%)
    percentage = models.DecimalField(max_digits=5, decimal_places=2)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.beneficiary.username} earned ₦{self.amount} from {self.source_user.username} (L{self.level})"


class APIProvider(models.Model):
    name = models.CharField(max_length=100, unique=True)
    base_url = models.CharField(max_length=255)
    auth_header_key = models.CharField(max_length=100, default='Authorization', help_text="e.g. Authorization or api-key")
    auth_header_value = models.CharField(max_length=255, help_text="e.g. Bearer Token_here or api_key_value")
    additional_headers = models.TextField(blank=True, default='{}', help_text="JSON format of extra headers if any")
    plans_endpoint = models.CharField(max_length=255, default='/plans', help_text="Endpoint to fetch data plans list")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Network(models.Model):
    choice_options = [
        ("MTN", "MTN"),
        ("Airtel", "Airtel"),
        ("GLO", "GLO"),
        ("9mobile", "9mobile"),
    ]
    name = models.CharField(max_length=240, choices=choice_options)
    data_api = models.ForeignKey(APIProvider, on_delete=models.SET_NULL, null=True, blank=True, related_name='data_networks')
    airtime_api = models.ForeignKey(APIProvider, on_delete=models.SET_NULL, null=True, blank=True, related_name='airtime_networks')

    def __str__(self):
        return self.name


class Data_price(models.Model):
    network = models.ForeignKey(Network, on_delete=models.CASCADE)
    price =  models.BigIntegerField(default=0, null=True)
    Duration = models.CharField(default=0, null=True)
    size=models.CharField(max_length=240, default='0mb')
    networkid=models.IntegerField(default=0, null=True)
    referral_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0.00)


class SiteSetting(models.Model):
    maintenance_mode = models.BooleanField(default=False)
    email_notifications = models.BooleanField(default=True)
    sms_notifications = models.BooleanField(default=True)
    auto_kyc = models.BooleanField(default=False)
    fraud_detection = models.BooleanField(default=True)
    min_airtime = models.DecimalField(max_digits=10, decimal_places=2, default=50)
    max_airtime = models.DecimalField(max_digits=10, decimal_places=2, default=50000)
    daily_wallet_limit = models.DecimalField(max_digits=12, decimal_places=2, default=500000)
    enable_static_va = models.BooleanField(default=True)
    enable_dynamic_va = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, created = cls.objects.get_or_create(pk=1)
        return obj


class DynamicVirtualAccount(models.Model):
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="dynamic_accounts")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reference = models.CharField(max_length=100, unique=True)
    account_number = models.CharField(max_length=20)
    bank_name = models.CharField(max_length=100)
    expiry_at = models.DateTimeField()
    status = models.CharField(max_length=20, default='active')  # active, completed, expired
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.user.username} - ₦{self.amount} - {self.status}"


class CableProvider(models.Model):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=50, unique=True)  # API code like 'dstv', 'gotv', 'startimes'
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class CablePlan(models.Model):
    provider = models.ForeignKey(CableProvider, on_delete=models.CASCADE, related_name='plans')
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=100)  # API plan code
    price = models.DecimalField(max_digits=10, decimal_places=2)
    duration = models.CharField(max_length=50)  # e.g., "1 month", "3 months"
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.provider.name} - {self.name} - ₦{self.price}"


class CableSubscription(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('cancelled', 'Cancelled'),
    ]

    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name='cable_subscriptions')
    provider = models.ForeignKey(CableProvider, on_delete=models.CASCADE)
    plan = models.ForeignKey(CablePlan, on_delete=models.CASCADE)
    smart_card_number = models.CharField(max_length=50)
    customer_reference = models.CharField(max_length=100, unique=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    api_response = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user.username} - {self.provider.name} - {self.smart_card_number}"
    
