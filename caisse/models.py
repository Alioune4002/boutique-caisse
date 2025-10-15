from django.db import models
from django.utils import timezone
from decimal import Decimal

class Produit(models.Model):
    nom = models.CharField(max_length=100)
    prix = models.DecimalField(max_digits=10, decimal_places=2)
    stock = models.IntegerField(default=0)

    def __str__(self):
        return self.nom

class Vente(models.Model):
    produit = models.ForeignKey(Produit, on_delete=models.CASCADE)
    quantite = models.IntegerField()
    date_vente = models.DateTimeField(default=timezone.now)
    total = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"Vente de {self.quantite} {self.produit.nom} le {self.date_vente}"

class Remise(models.Model):
    TYPE_CHOICES = [
        ('pourcentage', 'Pourcentage'),
        ('fixe', 'Valeur fixe'),
    ]
    type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    valeur = models.DecimalField(max_digits=10, decimal_places=2)
    appliquee_a_produit = models.ForeignKey(Produit, on_delete=models.CASCADE, related_name='remises', null=True, blank=True)
    appliquee_a_vente = models.ForeignKey(Vente, on_delete=models.CASCADE, null=True, blank=True)

    def appliquer(self, montant):
        if self.type == 'pourcentage':
            return montant * (self.valeur / 100)
        return self.valeur

class Paiement(models.Model):
    MODE_CHOICES = [
        ('especes', 'Espèces'),
        ('carte', 'Carte bancaire'),
        ('cheque', 'Chèque'),
    ]
    vente = models.ForeignKey(Vente, on_delete=models.CASCADE, related_name='paiements')
    mode = models.CharField(max_length=20, choices=MODE_CHOICES)
    montant_paye = models.DecimalField(max_digits=10, decimal_places=2)
    date_paiement = models.DateTimeField(default=timezone.now)

    def __str__(self):
        return f"Paiement {self.mode} pour vente {self.vente.id}"

class Reassort(models.Model):
    produit = models.ForeignKey(Produit, on_delete=models.CASCADE, related_name='reassorts')
    quantite_ajoutee = models.IntegerField()
    stock_avant = models.IntegerField()
    stock_apres = models.IntegerField()
    date_reassort = models.DateTimeField(default=timezone.now)
    utilisateur = models.ForeignKey('auth.User', on_delete=models.SET_NULL, null=True, blank=True)
    
    def save(self, *args, **kwargs):
        self.stock_avant = self.produit.stock
        self.produit.stock += self.quantite_ajoutee
        self.stock_apres = self.produit.stock
        self.produit.save()
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"Réassort {self.produit.nom}: +{self.quantite_ajoutee}"